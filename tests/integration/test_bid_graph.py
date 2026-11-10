"""
Integration tests: the real graphs, real MCP servers (in-memory), real GigSim (in-process),
fake LLM (so no API key is needed). Each test uses its own SQLite checkpoint file.
"""

import json
import os
import tempfile
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from agent import runtime as rt_mod
from agent.mcp_client import GigBidMCP
from agent.memory import store as memory
from gigsim import app as gigsim_app
from mcp_servers.marketplace import server as marketplace
from mcp_servers.marketplace.adapters.gigsim import GigSimAdapter
from mcp_servers.portfolio import server as portfolio
from mcp_servers.workspace import server as workspace

ROOT = Path(__file__).resolve().parents[2]
JOBS = {j["job_id"]: j for j in json.loads((ROOT / "data/gigsim/jobs.json").read_text(encoding="utf-8"))}
LABELS = json.loads((ROOT / "evals/datasets/dev_labels.json").read_text(encoding="utf-8"))
USER = "ml_engineer"
SETTINGS = rt_mod.default_settings(USER)
ADMIN = {"Authorization": "Bearer gigsim-admin-token"}


def job_of(kind: str, style: str = "detailed") -> dict:
    lab = next(lab for lab in LABELS if lab["persona_id"] == USER and lab["kind"] == kind
               and lab.get("post_style", "detailed") == style)
    return JOBS[lab["job_id"]]


@pytest.fixture(autouse=True)
def wired(monkeypatch):
    os.environ["GIGBID_FAKE_LLM"] = "1"
    TestClient(gigsim_app.app).post("/admin/reset", headers=ADMIN)
    # tests run much faster than a real user: lift both rate limits for the test only
    monkeypatch.setattr(marketplace.limiter, "per_minute", 10_000)
    monkeypatch.setattr(gigsim_app, "RATE_LIMIT", 10_000)
    marketplace._db.execute("DELETE FROM drafts")             # fresh marketplace draft store per test
    marketplace._db.commit()
    transport = httpx.ASGITransport(app=gigsim_app.app)
    monkeypatch.setattr(marketplace, "get_port",
                        lambda user: GigSimAdapter("http://gigsim", "gigsim-ml-token", transport=transport))
    monkeypatch.setattr(GigBidMCP, "default_in_memory",
                        {"portfolio": portfolio.mcp, "marketplace": marketplace.mcp, "workspace": workspace.mcp})
    yield os.path.join(tempfile.mkdtemp(prefix="gigbid-graph-"), "graph.sqlite")
    os.environ.pop("GIGBID_FAKE_LLM", None)


def connects() -> int:
    return TestClient(gigsim_app.app).get("/me/connects", headers={"Authorization": "Bearer gigsim-ml-token"}).json()["balance"]


async def test_scam_job_is_skipped_without_writing(wired):
    async with rt_mod.open_runtime(f"sqlite:///{wired}") as rt:
        snap = await rt_mod.start_bid(rt, USER, job_of("scam"), SETTINGS)
    v = snap["values"]
    assert v["risk"]["level"] == "high" and snap["status"] == "recommended_skip"
    assert "draft" not in v and snap["interrupt"] is None


async def test_good_job_pauses_for_approval_then_submits_once(wired):
    job = job_of("good")
    async with rt_mod.open_runtime(f"sqlite:///{wired}") as rt:
        snap = await rt_mod.start_bid(rt, USER, job, SETTINGS)
        assert snap["status"] == "awaiting_approval", snap["values"].get("error")
        payload = snap["interrupt"]
        assert {"draft", "claims", "risk", "price", "preview"} <= set(payload)
        assert payload["preview"]["connects_cost"] == job["connects_cost"]
        assert connects() == 100                                    # nothing spent before approval
        assert len(snap["values"]["critiques"]) <= 3                # Critic loop is bounded

        done = await rt_mod.resume_bid(rt, USER, job["job_id"], {"action": "approve"}, SETTINGS)
        again = await rt_mod.resume_bid(rt, USER, job["job_id"], {"action": "approve"}, SETTINGS)   # double click
    assert done["status"] == "submitted" and again["status"] == "submitted"
    assert connects() == 100 - job["connects_cost"]                # charged exactly once


async def test_crash_while_waiting_then_resume_submits_once(wired):
    """'Kill the API' = close the runtime; a NEW runtime on the same database resumes the thread."""
    job = job_of("good")
    async with rt_mod.open_runtime(f"sqlite:///{wired}") as rt:
        assert (await rt_mod.start_bid(rt, USER, job, SETTINGS))["status"] == "awaiting_approval"
    async with rt_mod.open_runtime(f"sqlite:///{wired}") as rt2:     # "restarted"
        snap = await rt_mod.resume_bid(rt2, USER, job["job_id"], {"action": "approve"}, SETTINGS)
        hist = await rt_mod.history(rt2, "bid", rt_mod.bid_thread(USER, job["job_id"]))
    assert snap["status"] == "submitted" and connects() == 100 - job["connects_cost"]
    assert len(hist) > 5                                            # every step was checkpointed


async def test_reject_with_reason_sends_nothing(wired):
    job = job_of("good")
    async with rt_mod.open_runtime(f"sqlite:///{wired}") as rt:
        await rt_mod.start_bid(rt, USER, job, SETTINGS)
        snap = await rt_mod.resume_bid(rt, USER, job["job_id"], {"action": "reject", "reason": "too far from my niche"},
                                       SETTINGS)
    assert snap["status"] == "rejected" and snap["values"]["approval"]["reason"] == "too far from my niche"
    assert connects() == 100


async def test_edits_are_rechecked_and_feed_style_memory(wired):
    async with rt_mod.open_runtime(f"sqlite:///{wired}") as rt:
        for n, kind in enumerate(["good", "injection"]):           # two different jobs, same kind of edit
            job = job_of(kind)
            snap = await rt_mod.start_bid(rt, USER, job, SETTINGS)
            letter = snap["interrupt"]["draft"]["cover_letter"]
            edited = letter.replace("reliable ", "")                 # user deletes the word "reliable"
            snap = await rt_mod.resume_bid(rt, USER, job["job_id"], {"action": "edit", "cover_letter": edited}, SETTINGS)
            assert snap["status"] == "awaiting_approval"            # back to approval after compliance re-check
            assert snap["interrupt"]["draft"]["edited_by_user"] is True
        rules = await memory.style_rules(rt.store, USER)
    assert any('"reliable"' in r for r in rules)                      # promoted after 2 separate edits


async def test_bad_edit_is_flagged_not_silently_sent(wired):
    job = job_of("good")
    async with rt_mod.open_runtime(f"sqlite:///{wired}") as rt:
        snap = await rt_mod.start_bid(rt, USER, job, SETTINGS)
        bad = snap["interrupt"]["draft"]["cover_letter"] + " Email me at sara@example.com."
        snap = await rt_mod.resume_bid(rt, USER, job["job_id"], {"action": "edit", "cover_letter": bad}, SETTINGS)
    assert snap["status"] == "awaiting_approval" and snap["values"]["compliance"]["passed"] is False


async def test_node_failure_goes_to_dead_letter(wired, monkeypatch):
    from agent import llm

    async def broken(*a, **k):
        raise RuntimeError("model down")
    monkeypatch.setattr(llm, "structured", broken)
    async with rt_mod.open_runtime(f"sqlite:///{wired}") as rt:
        snap = await rt_mod.start_bid(rt, USER, job_of("good"), SETTINGS)
    assert snap["status"] == "dead_letter" and "model down" in snap["values"]["error"]


async def test_step_budget_moves_thread_to_needs_attention(wired, monkeypatch):
    from agent.nodes import base

    monkeypatch.setitem(base.BUDGET, "max_graph_steps", 6)
    async with rt_mod.open_runtime(f"sqlite:///{wired}") as rt:
        snap = await rt_mod.start_bid(rt, USER, job_of("good"), SETTINGS)
    assert snap["status"] == "needs_attention"


async def test_conversation_reply_needs_approval_then_sends(wired):
    async with rt_mod.open_runtime(f"sqlite:///{wired}") as rt:
        # submit proposals to several good jobs until a client replies (GigSim reacts instantly in tests)
        thread = None
        for lab in [lab for lab in LABELS if lab["persona_id"] == USER and lab["kind"] == "good"][:8]:
            job = JOBS[lab["job_id"]]
            await rt_mod.start_bid(rt, USER, job, SETTINGS)
            await rt_mod.resume_bid(rt, USER, job["job_id"], {"action": "approve"}, SETTINGS)
            threads = await GigBidMCP(USER).call("client_liaison", "list_threads")
            if threads:
                thread = threads[0]["thread_id"]
                break
        assert thread, "no client replied"
        snap = await rt_mod.start_conversation(rt, USER, thread, SETTINGS)
        assert snap["status"] == "awaiting_approval" and snap["interrupt"]["reply"]
        done = await rt_mod.resume_conversation(rt, USER, thread, {"action": "approve"}, SETTINGS)
    assert done["status"] == "sent"
