"""
marketplace_port.py - the ONE interface for talking to any marketplace (requirement R1).

In simple words:
    A "port" is a plug socket. It says WHAT a marketplace must be able to do
    (search jobs, get a client's history, submit a proposal...), not HOW.
    Each marketplace gets an "adapter" that fits the socket:
        GigSimAdapter      -> talks to our simulator over HTTP
        UpworkLiveAdapter  -> talks to Upwork's official MCP server
    Which adapter is used is decided by config (marketplace.mode), so the
    agents never know or care which marketplace is behind the socket.

Technical terms: this is the "ports and adapters" (hexagonal) pattern.
"""

from typing import Any, Protocol


class MarketplaceUnavailable(Exception):
    """The marketplace cannot be reached right now (down, timing out, too many errors)."""


class MarketplaceError(Exception):
    """The marketplace answered, but refused the request (e.g. not enough Connects)."""

    def __init__(self, status: int, detail: str):
        super().__init__(f"{status}: {detail}")
        self.status, self.detail = status, detail


class MarketplacePort(Protocol):
    # --- read ---
    async def search_jobs(self, query: str = "", category: str | None = None,
                          posted_after: str | None = None, limit: int = 20) -> list[dict[str, Any]]: ...
    async def get_job(self, job_id: str) -> dict[str, Any]: ...
    async def get_client_history(self, client_id: str) -> dict[str, Any]: ...
    async def get_connects_balance(self) -> dict[str, Any]: ...
    async def get_policy(self) -> dict[str, Any]: ...
    async def market_stats(self, category: str) -> dict[str, Any]: ...
    async def list_proposals(self) -> list[dict[str, Any]]: ...
    async def list_threads(self) -> list[dict[str, Any]]: ...
    async def list_messages(self, thread_id: str) -> list[dict[str, Any]]: ...
    # --- write (always behind human approval; always with an idempotency key) ---
    async def preview_proposal(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def submit_proposal(self, payload: dict[str, Any], idempotency_key: str) -> dict[str, Any]: ...
    async def send_message(self, thread_id: str, text: str, idempotency_key: str) -> dict[str, Any]: ...


def get_marketplace(user_id: str, mode: str | None = None, **kwargs) -> MarketplacePort:
    """Factory: build the right adapter for this user, based on config."""
    from agent.settings import CONFIG, marketplace_mode

    mode = mode or marketplace_mode()
    if mode == "gigsim":
        import os

        from mcp_servers.marketplace.adapters.gigsim import GigSimAdapter

        cfg = CONFIG["marketplace"]
        token = cfg["dev_accounts"].get(user_id)
        if not token:
            raise MarketplaceError(401, f"no GigSim account connected for user {user_id}")
        return GigSimAdapter(os.getenv("GIGSIM_BASE_URL", cfg["gigsim_base_url"]), token,
                             timeout=cfg["timeout_seconds"], max_retries=cfg["max_retries"], **kwargs)
    if mode == "upwork_live":
        from mcp_servers.marketplace.adapters.upwork_live import UpworkLiveAdapter

        return UpworkLiveAdapter(user_id)
    raise ValueError(f"unknown marketplace mode: {mode}")
