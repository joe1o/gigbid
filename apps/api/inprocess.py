"""
inprocess.py - run GigSim and the 3 MCP servers INSIDE the API process (tests and demos only).

GIGBID_INPROCESS=1 swaps HTTP calls for in-memory MCP sessions and an in-process GigSim,
so the Playwright tests need no extra processes. Production runs every server as its own
process (scripts/run_all.py), so "kill the marketplace server" is a real kill.

`marketplace_down(True)` makes the marketplace unreachable, to test degraded mode.
"""

import httpx

from agent.mcp_client import GigBidMCP
from agent.settings import CONFIG

_state = {"down": False}


def marketplace_down(down: bool) -> None:
    _state["down"] = down


def wire() -> None:
    from gigsim import app as gigsim_app
    from mcp_servers.marketplace import server as marketplace
    from mcp_servers.marketplace.adapters.gigsim import GigSimAdapter
    from mcp_servers.portfolio import server as portfolio
    from mcp_servers.workspace import server as workspace

    transport = httpx.ASGITransport(app=gigsim_app.app)
    accounts = CONFIG["marketplace"]["dev_accounts"]

    def port(account: str):
        token = accounts.get(account, accounts["ml_engineer"])
        if _state["down"]:
            return GigSimAdapter("http://127.0.0.1:9", token, timeout=1, max_retries=0)   # nothing listens there
        return GigSimAdapter("http://gigsim", token, transport=transport)

    marketplace.get_port = port
    GigBidMCP.default_in_memory = {"portfolio": portfolio.mcp, "marketplace": marketplace.mcp,
                                   "workspace": workspace.mcp}
