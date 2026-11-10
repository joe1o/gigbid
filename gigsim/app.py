"""
app.py - GigSim, our fake freelance marketplace (a REST API built with FastAPI).

In simple words:
    This is a pretend Upwork. It has jobs, clients, Connects (bid credits),
    proposals and chat messages. GigBid's agents will talk to it (through our
    Marketplace MCP server in Phase 2) exactly as they would talk to a real
    marketplace. Like a real platform it also:
      - needs a login token        (Authorization: Bearer <token>)
      - limits how fast you call it (rate limit -> HTTP 429)
      - sometimes fails on purpose  (HTTP 503) so we can test error handling
      - releases new jobs over time (a "live feed")
      - has fake clients that reply, ask for interviews, or hire

Run:  uvicorn gigsim.app:app --port 8081
Docs: open http://localhost:8081/docs to see and try every endpoint.
"""

import json
import os
import random
import statistics
import time
import uuid
from collections import defaultdict, deque
from datetime import UTC, datetime
from pathlib import Path

import yaml
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from gigsim import client_sim
from gigsim.db import DB

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# 1. Load settings and data (once, when the server starts)
# ---------------------------------------------------------------------------
CFG = yaml.safe_load((HERE / "config.yaml").read_text(encoding="utf-8"))
ACCOUNTS: dict[str, str] = CFG["accounts"]                       # token -> freelancer id
ADMIN_TOKEN = os.getenv("GIGSIM_ADMIN_TOKEN", CFG["admin_token"])
RATE_LIMIT = int(os.getenv("GIGSIM_RATE_LIMIT", CFG["rate_limit_per_minute"]))
ERROR_RATE = float(os.getenv("GIGSIM_ERROR_RATE", CFG["error_rate"]))
REVEAL_S = float(os.getenv("GIGSIM_REVEAL_SECONDS", CFG["reveal_seconds"]))
RELEASE_ALL = os.getenv("GIGSIM_RELEASE_ALL", str(CFG["release_all_jobs"])).lower() == "true"
DB_PATH = os.getenv("GIGSIM_DB_PATH", str(ROOT / CFG["db_path"]))


def load_policy() -> dict:
    """Read policy.yaml fresh each time, so a policy change applies without a restart."""
    return yaml.safe_load((HERE / "policy.yaml").read_text(encoding="utf-8"))


JOBS = {j["job_id"]: j for j in json.loads((ROOT / "data/gigsim/jobs.json").read_text(encoding="utf-8"))}
CLIENTS = {c["client_id"]: c for c in
           json.loads((ROOT / "data/gigsim/clients.json").read_text(encoding="utf-8"))["clients"]}
HISTORY = json.loads((ROOT / "data/gigsim/market_history.json").read_text(encoding="utf-8"))

db = DB(DB_PATH)
if not db.q("SELECT 1 FROM meta WHERE k='started_at'"):     # first run: create balances
    db.reset(list(ACCOUNTS.values()), load_policy()["weekly_connects"])

app = FastAPI(title="GigSim", version="1.0",
              description="A small marketplace simulator used to develop and evaluate GigBid.")

# ---------------------------------------------------------------------------
# 2. Middleware: rate limit + random failures (runs before every request)
# ---------------------------------------------------------------------------
_calls: dict[str, deque] = defaultdict(deque)   # token -> timestamps of recent calls
FREE_PATHS = ("/health", "/admin", "/docs", "/openapi.json")


@app.middleware("http")
async def platform_behaviour(request: Request, call_next):
    if not request.url.path.startswith(FREE_PATHS):
        # Rate limit: at most RATE_LIMIT calls per 60 seconds per token.
        token = request.headers.get("authorization", "anon")
        now = time.time()
        q = _calls[token]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= RATE_LIMIT:
            return JSONResponse({"detail": "rate limit exceeded"}, status_code=429,
                                headers={"Retry-After": str(int(60 - (now - q[0])) + 1)})
        q.append(now)
        # Occasional server error, like a real platform having a bad moment.
        if random.random() < ERROR_RATE:
            return JSONResponse({"detail": "temporary server error, please retry"}, status_code=503)
    return await call_next(request)


# ---------------------------------------------------------------------------
# 3. Helpers
# ---------------------------------------------------------------------------
def current_freelancer(authorization: str = Header(default="")) -> str:
    """Turn 'Authorization: Bearer <token>' into a freelancer id, or reject with 401."""
    token = authorization.removeprefix("Bearer ").strip()
    if token not in ACCOUNTS:
        raise HTTPException(401, "missing or invalid bearer token")
    return ACCOUNTS[token]


def posted_at(job: dict) -> float:
    return db.started_at() + job["release_after_minutes"] * 60


def is_visible(job: dict) -> bool:
    """A job is visible once its release time has passed (the 'live feed')."""
    return RELEASE_ALL or time.time() >= posted_at(job)


def public_job(job: dict) -> dict:
    """The job as the outside world sees it (no internal release timer)."""
    out = {k: v for k, v in job.items() if k != "release_after_minutes"}
    out["posted_at"] = datetime.fromtimestamp(posted_at(job), UTC).isoformat()
    return out


def process_due_events() -> None:
    """
    Fire any client "timers" whose time has come.
    Instead of a background thread, we simply check the timers at the start of
    every request ("lazy" processing). Simple, and it survives restarts because
    timers are stored in the database.
    """
    for ev in db.q("SELECT * FROM events WHERE done=0 AND due_at<=? ORDER BY due_at", (time.time(),)):
        db.x("UPDATE events SET done=1 WHERE id=?", (ev["id"],))
        rows = db.q("SELECT * FROM proposals WHERE proposal_id=?", (ev["thread_id"],))
        if not rows:
            continue
        p = rows[0]
        decision = json.loads(p["decision"])
        job, client = JOBS[p["job_id"]], CLIENTS[JOBS[p["job_id"]]["client_id"]]

        if ev["kind"] == "viewed" and p["status"] == "submitted":
            db.x("UPDATE proposals SET status='viewed' WHERE proposal_id=?", (p["proposal_id"],))

        elif ev["kind"] == "decide":
            if decision["will_reply"]:
                db.add_message(p["proposal_id"], "client",
                               client_sim.first_reply(decision["reply_kind"], job, p["bid_amount"], client))
                db.x("UPDATE proposals SET status='replied', stage=1 WHERE proposal_id=?", (p["proposal_id"],))
            else:
                db.x("UPDATE proposals SET status='lost' WHERE proposal_id=?", (p["proposal_id"],))

        elif ev["kind"] == "client_followup" and p["status"] in ("replied", "interview"):
            last = db.q("SELECT text FROM messages WHERE thread_id=? AND sender='freelancer' "
                        "ORDER BY id DESC LIMIT 1", (p["proposal_id"],))
            if p["status"] == "interview":
                db.add_message(p["proposal_id"], "client", "Great, see you then.")
                continue
            text, status = client_sim.follow_up(decision["reply_kind"], p["stage"], last[0]["text"] if last else "")
            if decision["reply_kind"] in ("question", "negotiation") and p["stage"] == 1:
                decision["reply_kind"] = "interview"          # next step is booking a call
            db.add_message(p["proposal_id"], "client", text)
            db.x("UPDATE proposals SET status=?, stage=stage+1, decision=? WHERE proposal_id=?",
                 (status, json.dumps(decision), p["proposal_id"]))
            if status == "interview":
                db.schedule(REVEAL_S, "hire_decision", p["proposal_id"])

        elif ev["kind"] == "hire_decision" and p["status"] == "interview":
            if decision["will_hire"]:
                db.add_message(p["proposal_id"], "client", "We'd like to hire you! Sending the contract now.")
                db.x("UPDATE proposals SET status='hired' WHERE proposal_id=?", (p["proposal_id"],))
            else:
                db.add_message(p["proposal_id"], "client", "Thanks for your time. We went with another freelancer.")
                db.x("UPDATE proposals SET status='lost' WHERE proposal_id=?", (p["proposal_id"],))


def tick():
    """FastAPI dependency: process timers before handling the request."""
    process_due_events()


# ---------------------------------------------------------------------------
# 4. Request bodies (Pydantic validates them automatically)
# ---------------------------------------------------------------------------
class ProposalIn(BaseModel):
    job_id: str
    cover_letter: str = Field(min_length=20)
    bid_amount: float = Field(gt=0)
    screening_answers: list[str] = Field(default_factory=list)


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=3000)


# ---------------------------------------------------------------------------
# 5. Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"ok": True, "jobs": len(JOBS)}


@app.get("/policy")
def policy(_: str = Depends(current_freelancer)):
    """Platform rules and Connects pricing. Agents read this instead of hard-coding rules."""
    return load_policy()


@app.get("/jobs", dependencies=[Depends(tick)])
def search_jobs(_: str = Depends(current_freelancer),
                q: str = Query("", description="keywords matched against title, description and skills"),
                category: str | None = Query(None, description="ml | web | data"),
                posted_after: str | None = Query(None, description="ISO time; only newer jobs"),
                limit: int = Query(20, ge=1, le=100)):
    words = [w.lower() for w in q.split()]
    after = datetime.fromisoformat(posted_after).timestamp() if posted_after else 0
    out = []
    for job in JOBS.values():
        if not is_visible(job) or (category and job["category"] != category) or posted_at(job) <= after:
            continue
        hay = f"{job['title']} {job['description']} {' '.join(job['required_skills'])}".lower()
        if all(w in hay for w in words):
            out.append(public_job(job))
    out.sort(key=lambda j: j["posted_at"], reverse=True)   # newest first
    return out[:limit]


@app.get("/jobs/{job_id}")
def get_job(job_id: str, _: str = Depends(current_freelancer)):
    job = JOBS.get(job_id)
    if not job or not is_visible(job):
        raise HTTPException(404, "job not found")
    return public_job(job)


@app.get("/clients/{client_id}")
def get_client(client_id: str, _: str = Depends(current_freelancer)):
    """Public client history only. The client's hidden preferences are never returned."""
    c = CLIENTS.get(client_id)
    if not c:
        raise HTTPException(404, "client not found")
    return {"client_id": client_id, **c["public"]}


@app.get("/market/stats")
def market_stats(category: str, _: str = Depends(current_freelancer)):
    """Price statistics from historical jobs, used by the Pricing Strategist."""
    if category not in HISTORY:
        raise HTTPException(404, "unknown category")
    xs = HISTORY[category]
    qs = statistics.quantiles(xs, n=4)
    return {"category": category, "n": len(xs), "p25": qs[0], "median": qs[1], "p75": qs[2]}


@app.get("/me/connects", dependencies=[Depends(tick)])
def my_connects(fid: str = Depends(current_freelancer)):
    return {"freelancer_id": fid, "balance": db.q("SELECT balance FROM connects WHERE freelancer_id=?", (fid,))[0]["balance"]}


@app.post("/proposals", dependencies=[Depends(tick)])
def submit_proposal(body: ProposalIn,
                    fid: str = Depends(current_freelancer),
                    idempotency_key: str | None = Header(default=None),
                    dry_run: bool = Query(False, description="true = only preview what would be sent and its cost")):
    """
    Submit a proposal. Costs Connects.
    - dry_run=true: nothing is saved or spent; returns the exact payload and cost (for the approval screen).
    - Idempotency-Key header (required when not dry_run): sending the same key twice returns the
      first result again, so a retry can never submit twice or spend Connects twice.
    """
    job = JOBS.get(body.job_id)
    if not job or not is_visible(job):
        raise HTTPException(404, "job not found")
    pol = load_policy()
    if len(body.cover_letter) > pol["max_cover_letter_chars"]:
        raise HTTPException(422, f"cover letter longer than {pol['max_cover_letter_chars']} characters")
    cost = job["connects_cost"] + pol["extra_connects_per_proposal"]
    balance = db.q("SELECT balance FROM connects WHERE freelancer_id=?", (fid,))[0]["balance"]

    if dry_run:
        return {"dry_run": True, "would_send": body.model_dump(), "connects_cost": cost,
                "balance_before": balance, "balance_after": balance - cost, "policy_version": pol["version"]}

    if not idempotency_key:
        raise HTTPException(400, "Idempotency-Key header is required")
    if (saved := db.get_idem(idempotency_key, fid)) is not None:
        return saved                                   # retry of an earlier call: same answer, no new charge
    if db.q("SELECT 1 FROM proposals WHERE freelancer_id=? AND job_id=?", (fid, body.job_id)):
        raise HTTPException(409, "you already submitted a proposal to this job")
    if balance < cost:
        raise HTTPException(402, f"not enough Connects: need {cost}, have {balance}")

    pid = "prop-" + uuid.uuid4().hex[:10]
    decision = client_sim.decide(pid, body.cover_letter, body.bid_amount, job, CLIENTS[job["client_id"]])
    db.x("UPDATE connects SET balance=balance-? WHERE freelancer_id=?", (cost, fid))
    db.x("INSERT INTO proposals VALUES (?,?,?,?,?,?,?,?,?,?,?)",
         (pid, fid, body.job_id, body.cover_letter, body.bid_amount, json.dumps(body.screening_answers),
          cost, "submitted", 0, json.dumps(decision), time.time()))
    db.schedule(REVEAL_S * 0.3, "viewed", pid)       # client opens it a bit later...
    db.schedule(REVEAL_S, "decide", pid)              # ...and decides a bit after that
    result = {"proposal_id": pid, "status": "submitted", "connects_spent": cost, "balance_after": balance - cost}
    db.put_idem(idempotency_key, fid, result)
    return result


def _proposal_view(p: dict) -> dict:
    """What the freelancer can see about a proposal (not the hidden decision)."""
    return {k: p[k] for k in ["proposal_id", "job_id", "bid_amount", "connects_spent", "status"]} | {
        "submitted_at": datetime.fromtimestamp(p["created_at"], UTC).isoformat()}


@app.get("/proposals", dependencies=[Depends(tick)])
def list_proposals(fid: str = Depends(current_freelancer)):
    return [_proposal_view(p) for p in db.q("SELECT * FROM proposals WHERE freelancer_id=? ORDER BY created_at DESC", (fid,))]


@app.get("/proposals/{proposal_id}", dependencies=[Depends(tick)])
def get_proposal(proposal_id: str, fid: str = Depends(current_freelancer)):
    rows = db.q("SELECT * FROM proposals WHERE proposal_id=? AND freelancer_id=?", (proposal_id, fid))
    if not rows:
        raise HTTPException(404, "proposal not found")
    return _proposal_view(rows[0])


@app.get("/threads", dependencies=[Depends(tick)])
def list_threads(fid: str = Depends(current_freelancer)):
    """Conversations that have at least one client message (thread id = proposal id)."""
    out = []
    for p in db.q("SELECT * FROM proposals WHERE freelancer_id=? ORDER BY created_at DESC", (fid,)):
        msgs = db.q("SELECT sender, text FROM messages WHERE thread_id=? ORDER BY id", (p["proposal_id"],))
        if msgs:
            out.append({"thread_id": p["proposal_id"], "job_id": p["job_id"], "status": p["status"],
                        "client_id": JOBS[p["job_id"]]["client_id"], "last_message": msgs[-1],
                        "unanswered": msgs[-1]["sender"] == "client"})
    return out


@app.get("/threads/{thread_id}/messages", dependencies=[Depends(tick)])
def thread_messages(thread_id: str, fid: str = Depends(current_freelancer)):
    if not db.q("SELECT 1 FROM proposals WHERE proposal_id=? AND freelancer_id=?", (thread_id, fid)):
        raise HTTPException(404, "thread not found")
    return db.q("SELECT id, sender, text, created_at FROM messages WHERE thread_id=? ORDER BY id", (thread_id,))


@app.post("/threads/{thread_id}/messages", dependencies=[Depends(tick)])
def send_message(thread_id: str, body: MessageIn, fid: str = Depends(current_freelancer),
                 idempotency_key: str | None = Header(default=None)):
    """Freelancer sends a chat message. Same Idempotency-Key rules as proposals."""
    if not idempotency_key:
        raise HTTPException(400, "Idempotency-Key header is required")
    if (saved := db.get_idem(idempotency_key, fid)) is not None:
        return saved
    if not db.q("SELECT 1 FROM proposals WHERE proposal_id=? AND freelancer_id=?", (thread_id, fid)):
        raise HTTPException(404, "thread not found")
    db.add_message(thread_id, "freelancer", body.text)
    db.schedule(REVEAL_S, "client_followup", thread_id)
    result = {"thread_id": thread_id, "sent": True}
    db.put_idem(idempotency_key, fid, result)
    return result


@app.post("/admin/reset")
def admin_reset(authorization: str = Header(default="")):
    """Wipe all proposals/messages and restart the job feed clock (used by tests and evals)."""
    if authorization.removeprefix("Bearer ").strip() != ADMIN_TOKEN:
        raise HTTPException(401, "admin only")
    _calls.clear()
    db.reset(list(ACCOUNTS.values()), load_policy()["weekly_connects"])
    return {"reset": True}
