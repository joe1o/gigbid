"""
runtime.py - starts the graphs with DURABLE storage and runs them (requirement C6).

In simple words:
    A "checkpointer" saves the graph's state after every step into a database.
    If the app crashes or restarts, the graph continues from the last saved step -
    including a proposal that was waiting for approval.
    The "store" is the long-term memory database (style + outcome memory).

    DATABASE_URL = postgresql://...  -> Postgres (Neon) checkpointer + store  (deployment)
    anything else / empty            -> a local SQLite file                    (local dev, tests)

Helpers used by the API (Phase 5):
    start_bid / resume_bid / start_conversation / resume_conversation / retry / snapshot / history
"""

import json
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from langgraph.types import Command

from agent.graphs.bid_graph import build_bid_graph
from agent.graphs.conversation_graph import build_conversation_graph
from agent.settings import PROCESSED, ROOT


@dataclass
class Runtime:
    bid: Any            # compiled bid graph
    conv: Any           # compiled conversation graph
    store: Any          # long-term memory store
    backend: str        # "postgres" | "sqlite"


def _is_postgres(url: str) -> bool:
    return url.startswith(("postgres://", "postgresql://")) and "user:password@host" not in url


@asynccontextmanager
async def open_runtime(db_url: str | None = None):
    url = db_url if db_url is not None else os.getenv("DATABASE_URL", "")
    if _is_postgres(url):
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from langgraph.store.postgres.aio import AsyncPostgresStore
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool

        # A POOL of connections (not one shared connection): web requests no longer wait in line
        # behind a background graph run that is saving checkpoints. Small, to suit the free host.
        # prepare_threshold=0 because Neon's pooled endpoint (PgBouncer) cannot keep prepared statements.
        async with AsyncConnectionPool(url, min_size=1, max_size=int(os.getenv("GIGBID_DB_POOL", "5")), open=False,
                                       kwargs={"autocommit": True, "prepare_threshold": 0,
                                               "row_factory": dict_row}) as pool:
            saver, store = AsyncPostgresSaver(pool), AsyncPostgresStore(pool)
            await saver.setup()
            await store.setup()
            yield Runtime(build_bid_graph().compile(checkpointer=saver, store=store),
                          build_conversation_graph().compile(checkpointer=saver, store=store), store, "postgres")
    else:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        from langgraph.store.sqlite.aio import AsyncSqliteStore

        path = url.removeprefix("sqlite:///") if url.startswith("sqlite") else str(PROCESSED / "graph.sqlite")
        # SQLite allows one writer per file, so checkpoints and memory get separate files.
        store_path = path.rsplit(".", 1)[0] + "-store.sqlite"
        async with AsyncSqliteSaver.from_conn_string(path) as saver, AsyncSqliteStore.from_conn_string(store_path) as store:
            await saver.setup()
            await store.setup()
            yield Runtime(build_bid_graph().compile(checkpointer=saver, store=store),
                          build_conversation_graph().compile(checkpointer=saver, store=store), store, "sqlite")


# ---------------------------------------------------------------------------
# Settings and thread ids
# ---------------------------------------------------------------------------
def default_settings(persona_id: str) -> dict:
    """Defaults for a persona (the web app's onboarding overrides these per user)."""
    p = json.loads((ROOT / "data" / "personas" / persona_id / "portfolio.json").read_text(encoding="utf-8"))
    return {"persona": persona_id, "account": persona_id, "name": p["name"], "headline": p["headline"], "fixed_floor_usd": p["fixed_floor_usd"],
            "hourly_floor_usd": p["hourly_floor_usd"], "autonomy": "manual", "connects_weekly_budget": 60,
            "searches": [{"query": "", "category": p["category"]}]}


def bid_thread(user_id: str, job_id: str) -> str:
    return f"bid:{user_id}:{job_id}"


def conv_thread(user_id: str, thread_id: str) -> str:
    return f"conv:{user_id}:{thread_id}"


def run_config(thread_id: str, settings: dict, kind: str) -> dict:
    """LangGraph config: which thread, user settings, and tags/metadata that appear in traces."""
    return {"configurable": {"thread_id": thread_id, "settings": settings}, "recursion_limit": 80,
            "run_name": f"{kind}:{thread_id}", "tags": [kind], "metadata": {"thread_id": thread_id}}


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------
async def _run(graph, inp, cfg, on_event=None) -> dict:
    """Stream the graph; on_event(update) gets each node's output as it finishes (for live UI)."""
    async for update in graph.astream(inp, cfg, stream_mode="updates"):
        if on_event:
            await on_event(update)
    return await snapshot(graph, cfg)


async def snapshot(graph, cfg) -> dict:
    """Current status, state values and the pending approval (if the graph is paused)."""
    st = await graph.aget_state(cfg)
    pending = [i.value for t in st.tasks for i in t.interrupts]
    return {"thread_id": cfg["configurable"]["thread_id"], "status": st.values.get("status"),
            "values": st.values, "interrupt": pending[0] if pending else None, "next": list(st.next)}


async def start_bid(rt: Runtime, user_id: str, job: dict, settings: dict, force: bool = False, on_event=None):
    cfg = run_config(bid_thread(user_id, job["job_id"]), settings, "bid")
    return await _run(rt.bid, {"user_id": user_id, "job": job, "force_bid": force}, cfg, on_event)


async def resume_bid(rt: Runtime, user_id: str, job_id: str, decision: dict, settings: dict, on_event=None):
    """Answer a pending approval. Safe to call twice: a finished thread just returns its snapshot."""
    cfg = run_config(bid_thread(user_id, job_id), settings, "bid")
    snap = await snapshot(rt.bid, cfg)
    if not snap["interrupt"]:
        return snap
    return await _run(rt.bid, Command(resume=decision), cfg, on_event)


async def start_conversation(rt: Runtime, user_id: str, thread_id: str, settings: dict, on_event=None):
    cfg = run_config(conv_thread(user_id, thread_id), settings, "conversation")
    return await _run(rt.conv, {"user_id": user_id, "thread_id": thread_id, "status": "running",
                                "approval": {}, "slots": []}, cfg, on_event)


async def resume_conversation(rt: Runtime, user_id: str, thread_id: str, decision: dict, settings: dict,
                              on_event=None):
    cfg = run_config(conv_thread(user_id, thread_id), settings, "conversation")
    snap = await snapshot(rt.conv, cfg)
    if not snap["interrupt"]:
        return snap
    return await _run(rt.conv, Command(resume=decision), cfg, on_event)


async def retry(rt: Runtime, graph_name: str, thread_id: str, settings: dict, on_event=None):
    """Resume a thread that stopped on an error (e.g. marketplace was down) from its last checkpoint."""
    graph = rt.bid if graph_name == "bid" else rt.conv
    return await _run(graph, None, run_config(thread_id, settings, graph_name), on_event)


async def history(rt: Runtime, graph_name: str, thread_id: str) -> list[dict]:
    """Every checkpoint of a thread (newest first) - for replaying a job from any node."""
    graph = rt.bid if graph_name == "bid" else rt.conv
    cfg = {"configurable": {"thread_id": thread_id}}
    return [{"checkpoint_id": s.config["configurable"]["checkpoint_id"], "next": list(s.next),
             "status": s.values.get("status"), "step": s.metadata.get("step")}
            async for s in graph.aget_state_history(cfg)]


async def replay_from(rt: Runtime, graph_name: str, thread_id: str, checkpoint_id: str, settings: dict,
                      on_event=None):
    """Re-run a thread starting from an earlier checkpoint (time travel)."""
    graph = rt.bid if graph_name == "bid" else rt.conv
    cfg = run_config(thread_id, settings, graph_name)
    cfg["configurable"]["checkpoint_id"] = checkpoint_id
    return await _run(graph, None, cfg, on_event)
