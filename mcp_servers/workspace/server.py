"""
Workspace MCP server - the freelancer's calendar and email drafts (a LOCAL MOCK).

In simple words:
    When a client asks for an interview, the Client Liaison agent needs free
    times from the freelancer's calendar, can put a "tentative hold" on a time,
    and can prepare an email draft. The assignment allows a local mock instead
    of real Google Calendar/Gmail, as long as agents only see MCP tools - so
    this server fakes a calendar with a few fixed busy blocks, stored in SQLite.

    Tools: get_free_slots, create_interview_hold, create_email_draft
    Nothing here ever sends an email; drafts are only saved.

Run over HTTP:  python -m mcp_servers.workspace.server      (port 8093)
"""

import os
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from agent.settings import CONFIG, PROCESSED
from mcp_servers.common import AuditLog, caller

mcp = FastMCP("gigbid-workspace", instructions="Calendar availability, tentative holds and email drafts (mock).")
audit = AuditLog(PROCESSED / "audit" / "workspace.jsonl")

TZ = timezone(timedelta(hours=CONFIG["workspace"]["timezone_offset_hours"]))
START_H, END_H = CONFIG["workspace"]["work_hours"]

_db = sqlite3.connect(os.getenv("WORKSPACE_DB", str(PROCESSED / "workspace.sqlite")), check_same_thread=False)
_db.row_factory = sqlite3.Row
_lock = threading.Lock()
_db.executescript("""
CREATE TABLE IF NOT EXISTS holds (hold_id TEXT PRIMARY KEY, user_id TEXT, idem_key TEXT, start TEXT, end TEXT,
    title TEXT, status TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS holds_idem ON holds(user_id, idem_key);
CREATE TABLE IF NOT EXISTS email_drafts (draft_id TEXT PRIMARY KEY, user_id TEXT, idem_key TEXT, subject TEXT,
    body TEXT, created_at TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS email_idem ON email_drafts(user_id, idem_key);
""")


class Slot(BaseModel):
    start: str = Field(description="ISO time with timezone")
    end: str
    label: str = Field(description="human-friendly, e.g. 'Tuesday 11 Nov, 15:00'")


class Hold(BaseModel):
    hold_id: str
    start: str
    end: str
    title: str
    status: str = Field(description="always 'tentative' until the freelancer confirms")


class EmailDraft(BaseModel):
    draft_id: str
    subject: str
    body: str
    sent: bool = False


def _fixed_busy(day: datetime) -> list[tuple[datetime, datetime]]:
    """Pretend the freelancer is busy 13:00-14:00 every day and 10:00-12:00 on Tuesdays."""
    busy = [(day.replace(hour=13), day.replace(hour=14))]
    if day.weekday() == 1:
        busy.append((day.replace(hour=10), day.replace(hour=12)))
    return busy


def _overlaps(a0, a1, b0, b1) -> bool:
    return a0 < b1 and b0 < a1


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False))
def get_free_slots(ctx: Context,
                   days_ahead: Annotated[int, Field(ge=1, le=14)] = 5,
                   duration_minutes: Annotated[int, Field(ge=15, le=120)] = 30,
                   max_slots: Annotated[int, Field(ge=1, le=10)] = 4) -> list[Slot]:
    """Free weekday slots in working hours over the next few days, spread across different days."""
    user, trace = caller(ctx)
    with _lock:
        holds = [(datetime.fromisoformat(h["start"]), datetime.fromisoformat(h["end"]))
                 for h in _db.execute("SELECT start, end FROM holds WHERE user_id=?", (user,)).fetchall()]
    now = datetime.now(TZ)
    out = []
    for d in range(1, days_ahead + 1):
        day = (now + timedelta(days=d)).replace(minute=0, second=0, microsecond=0)
        if day.weekday() >= 5:                      # skip weekends
            continue
        busy = _fixed_busy(day) + holds
        t = day.replace(hour=START_H)
        while t + timedelta(minutes=duration_minutes) <= day.replace(hour=END_H):
            end = t + timedelta(minutes=duration_minutes)
            if not any(_overlaps(t, end, b0, b1) for b0, b1 in busy):
                out.append(Slot(start=t.isoformat(), end=end.isoformat(), label=t.strftime("%A %d %b, %H:%M")))
                break                               # one slot per day keeps suggestions varied
            t += timedelta(minutes=30)
        if len(out) >= max_slots:
            break
    audit.write(user, "get_free_slots", {"days_ahead": days_ahead}, [s.label for s in out], trace)
    return out


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True,
                                      openWorldHint=False))
def create_interview_hold(ctx: Context,
                          start: Annotated[str, Field(description="ISO start time from get_free_slots")],
                          title: Annotated[str, Field(min_length=3, max_length=120)],
                          idempotency_key: Annotated[str, Field(min_length=8, max_length=100)],
                          duration_minutes: Annotated[int, Field(ge=15, le=120)] = 30) -> Hold:
    """Put a TENTATIVE hold on the calendar for a proposed interview. Same key -> same hold."""
    user, trace = caller(ctx)
    try:
        s = datetime.fromisoformat(start)
    except ValueError as e:
        raise ToolError("start must be an ISO date-time, e.g. 2026-11-12T15:00:00+05:00") from e
    e = s + timedelta(minutes=duration_minutes)
    with _lock:
        row = _db.execute("SELECT * FROM holds WHERE user_id=? AND idem_key=?", (user, idempotency_key)).fetchone()
        if row:
            return Hold(**{k: row[k] for k in Hold.model_fields})
        hold = Hold(hold_id="hold-" + uuid.uuid4().hex[:8], start=s.isoformat(), end=e.isoformat(),
                    title=title, status="tentative")
        _db.execute("INSERT INTO holds VALUES (?,?,?,?,?,?,?)",
                    (hold.hold_id, user, idempotency_key, hold.start, hold.end, title, "tentative"))
        _db.commit()
    audit.write(user, "create_interview_hold", {"start": start, "title": title}, hold.model_dump(), trace)
    return hold


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True,
                                      openWorldHint=False))
def create_email_draft(ctx: Context,
                       subject: Annotated[str, Field(min_length=3, max_length=200)],
                       body: Annotated[str, Field(min_length=10, max_length=5000)],
                       idempotency_key: Annotated[str, Field(min_length=8, max_length=100)]) -> EmailDraft:
    """Save an email DRAFT for the freelancer (e.g. an interview reminder). Never sends anything."""
    user, trace = caller(ctx)
    with _lock:
        row = _db.execute("SELECT * FROM email_drafts WHERE user_id=? AND idem_key=?",
                          (user, idempotency_key)).fetchone()
        if row:
            return EmailDraft(draft_id=row["draft_id"], subject=row["subject"], body=row["body"])
        d = EmailDraft(draft_id="email-" + uuid.uuid4().hex[:8], subject=subject, body=body)
        _db.execute("INSERT INTO email_drafts VALUES (?,?,?,?,?,?)",
                    (d.draft_id, user, idempotency_key, subject, body, datetime.now(TZ).isoformat()))
        _db.commit()
    audit.write(user, "create_email_draft", {"subject": subject}, {"draft_id": d.draft_id}, trace)
    return d


if __name__ == "__main__":
    from mcp_servers.common import serve_http

    serve_http(mcp, port=int(os.getenv("WORKSPACE_MCP_PORT", "8093")))
