"""
serve_api.py - starts the FastAPI server with an event loop the Postgres driver can use.

Why this exists: on Windows, uvicorn creates a "Proactor" event loop, which the async
Postgres driver (psycopg) does not support. Here we start uvicorn ourselves on a "Selector"
loop on Windows. On Linux (Docker, CI) this is just a normal uvicorn start.

Usage: python scripts/serve_api.py [port]
"""

import asyncio
import os
import selectors
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.getenv("PORT", "8000"))
    server = uvicorn.Server(uvicorn.Config("apps.api.main:app", host="0.0.0.0", port=port, proxy_headers=True,
                                           forwarded_allow_ips="*"))
    if sys.platform == "win32":
        asyncio.run(server.serve(), loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()))
    else:
        asyncio.run(server.serve())
