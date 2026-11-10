"""Workspace MCP server tests through an in-memory MCP client."""

from datetime import datetime

from agent.mcp_client import GigBidMCP
from mcp_servers.workspace import server


def mcp_as() -> GigBidMCP:
    return GigBidMCP("ml_engineer", in_memory={"workspace": server.mcp})


async def test_free_slots_are_weekdays_in_work_hours():
    slots = await mcp_as().call("client_liaison", "get_free_slots", {"days_ahead": 7})
    assert slots
    for s in slots:
        t = datetime.fromisoformat(s["start"])
        assert t.weekday() < 5 and 9 <= t.hour < 17 and t.hour != 13   # 13:00 is lunch (busy)


async def test_hold_is_idempotent_and_blocks_the_slot():
    c = mcp_as()
    slot = (await c.call("client_liaison", "get_free_slots", {}))[0]
    args = {"start": slot["start"], "title": "Interview: churn model", "idempotency_key": "hold-key-1"}
    h1 = await c.call("client_liaison", "create_interview_hold", args)
    h2 = await c.call("client_liaison", "create_interview_hold", args)
    assert h1["hold_id"] == h2["hold_id"] and h1["status"] == "tentative"
    assert slot["start"] not in [s["start"] for s in await c.call("client_liaison", "get_free_slots", {})]


async def test_email_draft_is_never_sent():
    d = await mcp_as().call("client_liaison", "create_email_draft",
                            {"subject": "Interview Tuesday", "body": "Reminder: call at 15:00.",
                             "idempotency_key": "email-key-1"})
    assert d["sent"] is False
