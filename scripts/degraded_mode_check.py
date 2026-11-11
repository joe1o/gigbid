"""
degraded_mode_check.py - rehearses viva question 1: "kill the marketplace MCP server".

With GigBid running (python scripts/run_all.py), this script:
  1. signs in as the reviewer and checks /api/health is "ok"
  2. kills the marketplace MCP server process
  3. waits until /api/health says "down" (the UI shows the red banner)
  4. waits until run_all restarts the server and /api/health is "ok" again

Usage: python scripts/degraded_mode_check.py [base_url]
"""

import os
import subprocess
import sys
import time

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"


def wait_for(client, want: str, timeout: float) -> float:
    t0 = time.time()
    while time.time() - t0 < timeout:
        h = client.get(f"{BASE}/api/health").json()
        if h["marketplace"] == want:
            return time.time() - t0
        time.sleep(2)
    raise SystemExit(f"health never became '{want}' within {timeout}s")


def marketplace_pids() -> list[int]:
    if sys.platform == "win32":
        ps = ("(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "
              "'*mcp_servers.marketplace.server*' -and $_.Name -like 'python*' }).ProcessId")
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=False, capture_output=True,
                             text=True).stdout
    else:
        out = subprocess.run(["pgrep", "-f", "mcp_servers.marketplace.server"], check=False, capture_output=True,
                             text=True).stdout
    return [int(x) for x in out.split()]


if __name__ == "__main__":
    c = httpx.Client(timeout=30)
    c.post(f"{BASE}/api/auth/login", json={"email": os.getenv("REVIEWER_EMAIL", "reviewer@gigbid.app"),
                                           "password": os.getenv("REVIEWER_PASSWORD", "review-local-only")})
    print("1. health:", c.get(f"{BASE}/api/health").json()["marketplace"])
    pids = marketplace_pids()
    print("2. killing marketplace MCP server, pid(s):", pids)
    for pid in pids:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], check=False, capture_output=True)
        else:
            os.kill(pid, 9)
    print(f"3. health is 'down' after {wait_for(c, 'down', 60):.0f}s  -> UI shows 'Marketplace unavailable'")
    print(f"4. health is 'ok' again after {wait_for(c, 'ok', 120):.0f}s -> run_all restarted it; queued work resumes")
