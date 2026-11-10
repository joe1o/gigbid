"""
main.py - the GigBid web API (FastAPI) and the web app's host.

    /api/...     JSON API (typed; OpenAPI schema at /openapi.json, docs at /docs)
    /            the built React app (apps/web/dist), with client-side routing

On startup it opens the durable runtime (Postgres on Neon, or SQLite locally), preloads
the reviewer login, and starts the recovery loop that resumes queued work when the
marketplace comes back.

Run (dev):  uvicorn apps.api.main:app --reload --port 8000
"""

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import agent.settings  # noqa: F401  (loads .env; Windows event-loop fix)
from agent.runtime import open_runtime
from apps.api import services
from apps.api.auth.users import ensure_reviewer
from apps.api.routers import analytics, approvals, auth, jobs, messages, proposals, runs

WEB_DIST = Path(__file__).resolve().parents[1] / "web" / "dist"
TEST_MODE = os.getenv("GIGBID_TEST_MODE") == "1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.getenv("GIGBID_INPROCESS") == "1":
        from apps.api.inprocess import wire

        wire()
    async with open_runtime() as rt:
        app.state.rt = rt
        await ensure_reviewer(rt.store)
        loop = asyncio.create_task(services.recovery_loop(app))
        yield
        loop.cancel()


app = FastAPI(title="GigBid API", version="1.0.0", lifespan=lifespan,
              description="Multi-agent freelancer copilot: every proposal and message needs human approval.")
for r in (auth, jobs, approvals, runs, proposals, messages, analytics):
    app.include_router(r.router)


@app.get("/api/ping", tags=["meta"])
async def ping() -> dict:
    return {"ok": True}


if TEST_MODE:
    @app.post("/api/test/marketplace", tags=["test"])
    async def set_marketplace(down: bool) -> dict:
        """Test only: make the marketplace unreachable (degraded-mode test)."""
        from apps.api.inprocess import marketplace_down

        marketplace_down(down)
        services._health["at"] = 0          # forget the cached health result
        return {"down": down}


# ---- the React app (built files), with SPA fallback for client-side routes ----
if (WEB_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
async def spa(path: str):
    if path.startswith("api/"):
        raise HTTPException(404, "not found")
    f = WEB_DIST / path
    if path and f.is_file():
        return FileResponse(f)
    index = WEB_DIST / "index.html"
    if not index.exists():
        return {"message": "API is running. Build the web app (apps/web: npm run build) to serve the UI here."}
    return FileResponse(index)
