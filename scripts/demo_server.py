"""
demo_server.py - a throwaway GigBid server for recording the demo video.

Like scripts/e2e_server.py, but with the REAL models (needs GROQ_API_KEY in .env):
    - fresh temporary databases, so the live site's data and logins are never touched
    - GigSim and the 3 MCP servers in-process
    - simulated clients reply within seconds (GIGSIM_REVEAL_SECONDS=4) so a reply can be shown
    - local-only reviewer login (reviewer@gigbid.app / review-local-only)

Usage: python scripts/demo_server.py [port]      (default 8020)
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
tmp = tempfile.mkdtemp(prefix="gigbid-demo-")
os.environ.update({
    "GIGBID_INPROCESS": "1", "GIGSIM_RELEASE_ALL": "true", "GIGSIM_REVEAL_SECONDS": "4", "GIGSIM_ERROR_RATE": "0",
    "DATABASE_URL": f"sqlite:///{tmp}/app.sqlite", "GIGSIM_DB_PATH": f"{tmp}/gigsim.sqlite",
    "MARKETPLACE_MCP_DB": f"{tmp}/marketplace.sqlite", "WORKSPACE_DB": f"{tmp}/workspace.sqlite",
    "REVIEWER_EMAIL": "reviewer@gigbid.app", "REVIEWER_PASSWORD": "review-local-only",
    "LANGSMITH_TRACING": "false", "GIGBID_RUN_SLOTS": "3", "GIGBID_SCHEDULER": "0",
})
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("apps.api.main:app", host="127.0.0.1", port=int(sys.argv[1]) if len(sys.argv) > 1 else 8020)
