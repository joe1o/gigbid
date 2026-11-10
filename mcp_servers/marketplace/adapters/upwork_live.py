"""
upwork_live.py - adapter for Upwork's official MCP server (live mode).

In simple words:
    Upwork runs its own MCP server at https://mcp.upwork.com/mcp. Signing in uses
    OAuth 2.1 (the "Log in with Upwork" flow); the resulting access token is stored
    ENCRYPTED per user and sent as a bearer token. We connect with
    MultiServerMCPClient over Streamable HTTP and map Upwork's tools onto the same
    methods as GigSimAdapter, so the agents cannot tell the difference.

Status: STUB. I do not have an Upwork account, so the OAuth flow and the exact
Upwork tool names are not verified. Live mode is never graded on outcomes. Every
write on Upwork is a DRAFT that the user must confirm on Upwork itself.
No scraping, no browser automation, no session cookies - only the official server.
"""

from agent.marketplace_port import MarketplaceUnavailable

# How our port methods would map onto Upwork MCP tools (names to be confirmed
# against Upwork's tool list once connected).
TOOL_MAP = {
    "search_jobs": "search_jobs",
    "get_job": "get_job_details",
    "submit_proposal": "create_proposal_draft",   # Upwork only creates drafts; user confirms on Upwork
    "send_message": "create_message_draft",
    "list_threads": "list_rooms",
    "list_messages": "list_messages",
}


class UpworkLiveAdapter:
    def __init__(self, user_id: str):
        self.user_id = user_id

    def __getattr__(self, name):
        async def not_connected(*args, **kwargs):
            raise MarketplaceUnavailable(
                "Upwork live mode is not connected: complete the Upwork OAuth sign-in in Settings first.")
        return not_connected
