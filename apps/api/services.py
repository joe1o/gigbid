"""
services.py - what the API actually does with the agents.

    run_bid / run_conv   : run a graph in the BACKGROUND (never inside the web request), stream
                           its progress to the browser, then save a short summary for the inbox.
    scout_now            : the Scout finds new jobs and starts one bid graph per job.
    recovery_loop        : degraded mode. Jobs that stopped because the marketplace was down
                           are marked "queued"; every 30 s, once the marketplace is back, they
                           resume from their last checkpoint.
    marketplace_health   : is the marketplace reachable right now? (drives the UI banner)

A semaphore limits how many graphs run at once, to stay inside the model provider's
and the marketplace's rate limits.
"""

import asyncio
import time

from agent import runtime as R
from agent.marketplace_port import MarketplaceUnavailable
from agent.mcp_client import GigBidMCP, ServerUnavailable
from agent.nodes.scout import scout
from apps.api.streaming import hub

RUN_SLOTS = asyncio.Semaphore(2)
_tasks: set[asyncio.Task] = set()


def launch(coro) -> None:
    """Start a background task and keep a reference so it is not garbage-collected."""
    t = asyncio.create_task(coro)
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)


# ---------------------------------------------------------------------------
# Job summaries (the inbox reads these; one record per job per user)
# ---------------------------------------------------------------------------
def summarise(job: dict, snap: dict | None, old: dict | None = None) -> dict:
    v = (snap or {}).get("values", {}) or {}
    old = old or {}
    usage = v.get("usage", [])
    price = v.get("price") or {}
    risk, fit, dec = v.get("risk") or {}, v.get("fit") or {}, v.get("decision") or {}
    approval = v.get("approval") or {}
    return {
        "job_id": job["job_id"], "thread_id": old.get("thread_id", ""),
        "title": job["title"], "category": job["category"],
        "budget_min": job["budget"]["min"], "budget_max": job["budget"]["max"],
        "connects_cost": job["connects_cost"], "posted_at": job.get("posted_at"),
        "status": (snap or {}).get("status") or old.get("status", "analysing"),
        "fit": fit.get("score", old.get("fit")), "risk_level": risk.get("level", old.get("risk_level")),
        "risk_flags": risk.get("flags", old.get("risk_flags", [])),
        "action": dec.get("action", old.get("action")), "reasons": dec.get("reasons", old.get("reasons", [])),
        "price": price.get("amount", old.get("price")),
        "proposal_id": (v.get("submission") or {}).get("proposal_id", old.get("proposal_id")),
        "tokens": sum(u["input_tokens"] + u["output_tokens"] for u in usage),
        "cost_usd": round(sum(u["cost_usd"] for u in usage), 6),
        "agent_seconds": old.get("agent_seconds", 0.0),
        "rejection_reason": approval.get("reason") if approval.get("action") == "reject" else old.get("rejection_reason"),
        "error": v.get("error") or None, "updated_at": time.time(),
    }


async def get_summary(store, user_id: str, job_id: str) -> dict | None:
    item = await store.aget(("jobs", user_id), job_id)
    return item.value if item else None


async def save_summary(store, user_id: str, summary: dict) -> None:
    await store.aput(("jobs", user_id), summary["job_id"], summary)


# ---------------------------------------------------------------------------
# Running graphs in the background
# ---------------------------------------------------------------------------
async def run_bid(rt, user: dict, job: dict, mode: str = "start", decision: dict | None = None,
                  force: bool = False) -> None:
    uid, settings = user["user_id"], user["settings"]
    thread = R.bid_thread(uid, job["job_id"])
    old = await get_summary(rt.store, uid, job["job_id"]) or {"thread_id": thread, "status": "analysing"}
    old["thread_id"] = thread
    hub.publish(thread, {"type": "start", "label": {"start": "Analysis started", "resume": "Resuming after your decision",
                                                    "retry": "Retrying"}[mode]})
    t0, snap = time.perf_counter(), None
    try:
        async with RUN_SLOTS:
            on = hub.on_update(thread)
            if mode == "start":
                snap = await R.start_bid(rt, uid, job, settings, force=force, on_event=on)
            elif mode == "resume":
                snap = await R.resume_bid(rt, uid, job["job_id"], decision, settings, on_event=on)
            else:
                snap = await R.retry(rt, "bid", thread, settings, on_event=on)
    except (MarketplaceUnavailable, ServerUnavailable) as e:
        snap = await R.snapshot(rt.bid, R.run_config(thread, settings, "bid"))
        snap["status"] = "queued"
        snap.setdefault("values", {})["error"] = f"paused: {e}. Will resume automatically."
    except Exception as e:  # noqa: BLE001  (never crash the server because one run failed)
        snap = {"status": "error", "values": {"error": f"{type(e).__name__}: {e}"}}
    summary = summarise(job, snap, old)
    summary["agent_seconds"] = round(old.get("agent_seconds", 0.0) + time.perf_counter() - t0, 2)
    await save_summary(rt.store, uid, summary)
    hub.publish(thread, {"type": "done", "status": summary["status"], "label": f"Run finished: {summary['status']}"})


async def run_conv(rt, user: dict, thread_id: str, decision: dict | None = None) -> None:
    uid, settings = user["user_id"], user["settings"]
    thread = R.conv_thread(uid, thread_id)
    hub.publish(thread, {"type": "start", "label": "Reading the conversation" if decision is None else "Applying your decision"})
    try:
        async with RUN_SLOTS:
            on = hub.on_update(thread)
            if decision is None:
                snap = await R.start_conversation(rt, uid, thread_id, settings, on_event=on)
            else:
                snap = await R.resume_conversation(rt, uid, thread_id, decision, settings, on_event=on)
        status = snap["status"]
    except (MarketplaceUnavailable, ServerUnavailable):
        status = "queued"
    except Exception as e:  # noqa: BLE001
        status = "error"
        hub.publish(thread, {"type": "node", "node": "error", "label": "Error", "detail": str(e)})
    await rt.store.aput(("conv_status", uid), thread_id, {"status": status, "updated_at": time.time()})
    hub.publish(thread, {"type": "done", "status": status, "label": f"Run finished: {status}"})


async def scout_now(rt, user: dict) -> dict:
    s = user["settings"]
    found = await scout(rt.store, user["user_id"], s.get("searches") or [{"query": ""}],
                        persona=s.get("persona"), account=s.get("account"))
    for job in found["new"]:
        summary = summarise(job, None, {"thread_id": R.bid_thread(user["user_id"], job["job_id"])})
        await save_summary(rt.store, user["user_id"], summary)
        launch(run_bid(rt, user, job))
    return {"new_jobs": len(found["new"]), "duplicates": len(found["duplicates"])}


# ---------------------------------------------------------------------------
# Degraded mode: health + automatic recovery
# ---------------------------------------------------------------------------
_health = {"at": 0.0, "ok": True, "detail": ""}


async def marketplace_health(force: bool = False) -> dict:
    if not force and time.time() - _health["at"] < 10:
        return _health
    try:
        await asyncio.wait_for(GigBidMCP("health-check", persona="ml_engineer").call("risk_assessor", "get_policy"), 8)
        _health.update(at=time.time(), ok=True, detail="")
    except Exception as e:  # noqa: BLE001
        _health.update(at=time.time(), ok=False, detail=f"{type(e).__name__}: {str(e)[:120]}")
    return _health


async def recovery_loop(app) -> None:
    from apps.api.auth.users import get_user

    while True:
        await asyncio.sleep(30)
        try:
            if not (await marketplace_health(force=True))["ok"]:
                continue
            rt = app.state.rt
            for u in await rt.store.asearch(("users",), limit=1000):
                queued = [i.value for i in await rt.store.asearch(("jobs", u.key), limit=500)
                          if i.value["status"] == "queued"]
                user = await get_user(rt.store, u.key)
                for summary in queued:
                    job = (await R.snapshot(rt.bid, R.run_config(summary["thread_id"], user["settings"], "bid")))["values"].get("job")
                    if job:
                        launch(run_bid(rt, user, job, mode="retry"))
        except Exception:  # noqa: BLE001, S112  (the loop must keep running)
            continue
