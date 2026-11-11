"""
run_all.py - starts every GigBid process, each as its OWN process, and keeps them running.

    gigsim       :8081  marketplace simulator
    portfolio    :8091  Portfolio MCP server
    marketplace  :8092  Marketplace MCP server
    workspace    :8093  Workspace MCP server
    api          :$PORT web API + the built web app (default 8000)

It is a tiny "supervisor": if a process dies it is restarted after RESTART_DELAY seconds.
That is what makes the viva demo work - kill the marketplace MCP server, the UI shows
"marketplace unavailable", work is queued, and ~20 s later everything recovers on its own.

Used both locally (`python scripts/run_all.py`) and in the Docker image.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
PORT = os.getenv("PORT", "8000")
RESTART_DELAY = int(os.getenv("RESTART_DELAY", "20"))

SERVICES = {
    "gigsim": [PY, "-m", "uvicorn", "gigsim.app:app", "--host", "127.0.0.1", "--port", "8081", "--log-level", "warning"],
    "portfolio": [PY, "-m", "mcp_servers.portfolio.server"],
    "marketplace": [PY, "-m", "mcp_servers.marketplace.server"],
    "workspace": [PY, "-m", "mcp_servers.workspace.server"],
    "api": [PY, "scripts/serve_api.py", PORT],          # uvicorn on a Postgres-friendly event loop
}


def start(name: str) -> subprocess.Popen:
    print(f"[run_all] starting {name}", flush=True)
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    return subprocess.Popen(SERVICES[name], cwd=ROOT, env=env)


def main() -> None:
    procs = {name: start(name) for name in SERVICES}
    died_at: dict[str, float] = {}

    def stop(*_):
        for p in procs.values():
            p.terminate()
        sys.exit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while True:
        time.sleep(2)
        for name, p in procs.items():
            if p.poll() is None:
                continue
            died_at.setdefault(name, time.time())
            if time.time() - died_at[name] >= RESTART_DELAY:      # restart after a pause
                print(f"[run_all] {name} exited ({p.returncode}); restarting", flush=True)
                procs[name] = start(name)
                died_at.pop(name, None)


if __name__ == "__main__":
    main()
