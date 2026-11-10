"""
e2e_server.py - starts a throwaway GigBid server for the Playwright end-to-end tests.

Everything runs in one process with a fake LLM and fresh temporary databases, so the
browser tests are fast, free and repeatable:
    GIGBID_INPROCESS=1  -> GigSim + 3 MCP servers inside the API process
    GIGBID_FAKE_LLM=1   -> canned model answers (no API key needed)
    GIGBID_TEST_MODE=1  -> enables /api/test/marketplace (to test the degraded-mode banner)

Usage: python scripts/e2e_server.py [port]
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
tmp = tempfile.mkdtemp(prefix="gigbid-e2e-")
os.environ.update({
    "GIGBID_INPROCESS": "1", "GIGBID_FAKE_LLM": "1", "GIGBID_TEST_MODE": "1",
    "GIGSIM_RELEASE_ALL": "true", "GIGSIM_REVEAL_SECONDS": "2", "GIGSIM_ERROR_RATE": "0",
    "DATABASE_URL": f"sqlite:///{tmp}/app.sqlite", "GIGSIM_DB_PATH": f"{tmp}/gigsim.sqlite",
    "MARKETPLACE_MCP_DB": f"{tmp}/marketplace.sqlite", "WORKSPACE_DB": f"{tmp}/workspace.sqlite",
    "REVIEWER_EMAIL": "reviewer@gigbid.app", "REVIEWER_PASSWORD": "review-local-only",
    "LANGSMITH_TRACING": "false", "GIGBID_RUN_SLOTS": "8",
})
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

if __name__ == "__main__":
    import uvicorn

    from gigsim import app as gigsim_app
    from mcp_servers.marketplace import server as marketplace

    gigsim_app.RATE_LIMIT = 10_000              # the browser tests go faster than a person
    marketplace.limiter.per_minute = 10_000
    uvicorn.run("apps.api.main:app", host="127.0.0.1", port=int(sys.argv[1]) if len(sys.argv) > 1 else 8010)
