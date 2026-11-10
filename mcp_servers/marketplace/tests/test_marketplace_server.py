"""
Marketplace MCP server tests, through an IN-MEMORY MCP client (no HTTP, no ports).
GigSim also runs in-process (httpx ASGITransport), so the whole chain is real:
    agent client -> MCP tool -> marketplace port -> GigSim adapter -> GigSim
"""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from agent.marketplace_port import MarketplaceUnavailable
from agent.mcp_client import GigBidMCP, ToolCallError, ToolNotAllowed
from agent.settings import PROCESSED
from gigsim import app as gigsim_app
from mcp_servers.marketplace import server
from mcp_servers.marketplace.adapters.gigsim import GigSimAdapter

LETTER = ("Churn on imbalanced data is where most models fail. I built a scikit-learn churn model "
          "for a telecom client with 120k users and cut churn by 9% in one quarter.")


@pytest.fixture(autouse=True)
def wired(monkeypatch):
    """Fresh GigSim, and point the MCP server's adapter at the in-process GigSim."""
    TestClient(gigsim_app.app).post("/admin/reset", headers={"Authorization": "Bearer gigsim-admin-token"})
    transport = httpx.ASGITransport(app=gigsim_app.app)
    monkeypatch.setattr(server, "get_port",
                        lambda user: GigSimAdapter("http://gigsim", "gigsim-ml-token", transport=transport))


def mcp_as() -> GigBidMCP:
    return GigBidMCP("ml_engineer", in_memory={"marketplace": server.mcp})


async def first_job_id() -> str:
    return (await mcp_as().call("scout", "search_jobs", {"query": "churn", "category": "ml"}))[0]["job_id"]


async def test_search_jobs_returns_typed_jobs():
    jobs = await mcp_as().call("scout", "search_jobs", {"category": "ml", "limit": 5})
    assert len(jobs) == 5 and {"job_id", "budget", "connects_cost", "client_id"} <= set(jobs[0])


async def test_allowlist_blocks_wrong_agent():
    with pytest.raises(ToolNotAllowed):
        await mcp_as().call("risk_assessor", "submit_proposal", {})


async def test_bad_input_is_rejected_by_schema():
    with pytest.raises(ToolCallError):
        await mcp_as().call("submitter", "create_proposal_draft",
                            {"job_id": "job-001", "cover_letter": "too short", "bid_amount": 100,
                             "idempotency_key": "key-12345"})


async def test_draft_preview_then_submit_exactly_once():
    c = mcp_as()
    job_id = await first_job_id()
    draft = await c.call("submitter", "create_proposal_draft",
                         {"job_id": job_id, "cover_letter": LETTER, "bid_amount": 500, "idempotency_key": "draft-key-1"})
    again = await c.call("submitter", "create_proposal_draft",
                         {"job_id": job_id, "cover_letter": LETTER, "bid_amount": 500, "idempotency_key": "draft-key-1"})
    assert draft["draft_id"] == again["draft_id"]                     # same key -> same draft
    cost = draft["preview"]["connects_cost"]

    dry = await c.call("submitter", "submit_proposal", {"draft_id": draft["draft_id"],
                                                        "idempotency_key": "submit-key-1", "dry_run": True})
    assert dry["dry_run"] and dry["preview"]["balance_after"] == 100 - cost

    first = await c.call("submitter", "submit_proposal", {"draft_id": draft["draft_id"], "idempotency_key": "submit-key-1"})
    second = await c.call("submitter", "submit_proposal", {"draft_id": draft["draft_id"], "idempotency_key": "submit-key-1"})
    assert first["proposal_id"] == second["proposal_id"]               # submitted exactly once
    assert (await c.call("pricing", "get_connects_balance"))["balance"] == 100 - cost


async def test_audit_log_masks_personal_data():
    await mcp_as().call("submitter", "create_proposal_draft",
                        {"job_id": await first_job_id(), "cover_letter": LETTER + " Mail me: sara@example.com",
                         "bid_amount": 500, "idempotency_key": "draft-key-pii"})
    last = (PROCESSED / "audit" / "marketplace.jsonl").read_text(encoding="utf-8").strip().splitlines()[-1]
    entry = json.loads(last)
    assert entry["tool"] == "create_proposal_draft" and "sara@example.com" not in last and "[email]" in last


async def test_degraded_mode_when_marketplace_is_down(monkeypatch):
    # Point the adapter at a port where nothing is listening.
    monkeypatch.setattr(server, "get_port",
                        lambda user: GigSimAdapter("http://127.0.0.1:9", "gigsim-ml-token", timeout=1, max_retries=0))
    with pytest.raises(MarketplaceUnavailable):
        await mcp_as().call("scout", "search_jobs", {})
