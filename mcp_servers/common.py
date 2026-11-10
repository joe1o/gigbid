"""
common.py - small helpers shared by our three MCP servers.

    caller(ctx)         -> who is calling (user id) and the trace id of the request
    RateLimiter         -> per-user limit on calls per minute
    AuditLog            -> append-only log of every tool call (user, tool, args, result, trace id)
    mask_pii(text)      -> hides emails, phone numbers and card numbers before anything is logged
    serve_http(...)     -> runs a server over HTTP with a required bearer token
"""

import json
import os
import re
import time
import uuid
from collections import defaultdict, deque
from contextvars import ContextVar
from pathlib import Path

from mcp.server.fastmcp import Context, FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

import agent.settings  # noqa: F401  (importing it loads the .env file for every server)

# ---------------------------------------------------------------------------
# Who is calling?
# ---------------------------------------------------------------------------
DEFAULT_USER = os.getenv("MCP_DEFAULT_USER", "ml_engineer")

# When servers run IN-PROCESS (tests, the API's test mode) there are no HTTP headers,
# so the client puts the same information here instead: {"user", "persona", "trace"}.
IN_PROCESS_CALLER: ContextVar[dict | None] = ContextVar("in_process_caller", default=None)


def _headers(ctx: Context | None) -> dict:
    try:
        request = ctx.request_context.request if ctx else None
    except (AttributeError, ValueError, LookupError):
        request = None
    if request is not None:
        return {"user": request.headers.get("x-gigbid-user"), "persona": request.headers.get("x-gigbid-persona"),
                "account": request.headers.get("x-gigbid-account"),
                "trace": request.headers.get("x-trace-id")}
    return IN_PROCESS_CALLER.get() or {}


def caller(ctx: Context | None) -> tuple[str, str]:
    """
    Return (user_id, trace_id) for the current tool call.
    Over HTTP, GigBid sends them as headers: X-GigBid-User and X-Trace-Id.
    Without them (unit tests) we fall back to a default user and a new trace id.
    """
    h = _headers(ctx)
    return h.get("user") or DEFAULT_USER, h.get("trace") or uuid.uuid4().hex


def caller_account(ctx: Context | None) -> str:
    """Which MARKETPLACE account to act as (X-GigBid-Account); defaults to the persona."""
    h = _headers(ctx)
    return h.get("account") or h.get("persona") or h.get("user") or DEFAULT_USER


def caller_persona(ctx: Context | None) -> str:
    """Which persona/portfolio + marketplace account this user works as (X-GigBid-Persona)."""
    h = _headers(ctx)
    return h.get("persona") or h.get("user") or DEFAULT_USER


# ---------------------------------------------------------------------------
# PII masking (personal data never goes into logs)
# ---------------------------------------------------------------------------
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_PHONE = re.compile(r"\+?\d[\d\s()-]{8,}\d")


def mask_pii(text: str) -> str:
    """Replace emails, card numbers and phone numbers with placeholders."""
    text = _EMAIL.sub("[email]", text)
    text = _CARD.sub("[card]", text)
    return _PHONE.sub("[phone]", text)


# ---------------------------------------------------------------------------
# Per-user rate limiter
# ---------------------------------------------------------------------------
class RateLimiter:
    """Allows at most `per_minute` calls per user in any 60-second window."""

    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self.calls: dict[str, deque] = defaultdict(deque)

    def check(self, user: str) -> None:
        now = time.time()
        q = self.calls[user]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= self.per_minute:
            raise RuntimeError("RATE_LIMITED: too many marketplace calls this minute, try again shortly")
        q.append(now)


# ---------------------------------------------------------------------------
# Append-only audit log
# ---------------------------------------------------------------------------
class AuditLog:
    """
    Writes one JSON line per tool call to a .jsonl file. We only ever append,
    never edit or delete, so the log is a trustworthy record of what happened.
    """

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, user: str, tool: str, arguments: dict, result, trace_id: str) -> None:
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            "user": user, "tool": tool, "trace_id": trace_id,
            "arguments": json.loads(mask_pii(json.dumps(arguments, default=str))),
            "result": mask_pii(json.dumps(result, default=str))[:2000],   # keep lines short
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------------------
# Run over HTTP with bearer-token auth
# ---------------------------------------------------------------------------
class BearerAuth(BaseHTTPMiddleware):
    """Rejects any HTTP request that does not carry 'Authorization: Bearer <MCP_AUTH_TOKEN>'."""

    def __init__(self, app, token: str):
        super().__init__(app)
        self.token = token

    async def dispatch(self, request, call_next):
        if request.headers.get("authorization", "") != f"Bearer {self.token}":
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)


def serve_http(mcp: FastMCP, port: int, require_auth: bool = True) -> None:
    """Start the MCP server on http://0.0.0.0:<port>/mcp (Streamable HTTP transport)."""
    import uvicorn

    app = mcp.streamable_http_app()
    token = os.getenv("MCP_AUTH_TOKEN", "")
    if require_auth:
        if not token or token == "replace_me":
            raise SystemExit("Set MCP_AUTH_TOKEN in .env before starting the server over HTTP.")
        app.add_middleware(BearerAuth, token=token)
    uvicorn.run(app, host="0.0.0.0", port=port)
