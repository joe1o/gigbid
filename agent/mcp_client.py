"""
mcp_client.py - how agents call MCP tools (requirement A6, "client discipline").

In simple words:
    1. Allowlists: each agent may only use the tools it needs (filtered by name).
       e.g. the Risk Assessor can read client history but can never submit a proposal.
    2. Timeouts: a tool call that takes too long is abandoned.
    3. Bounded retries with backoff: if a server can't be reached, try again a few
       times, waiting longer each time, then give up.
    4. Degraded mode: if the marketplace is down we raise MarketplaceUnavailable;
       the graph parks the job in a queue and the UI shows "marketplace unavailable".

Technically: we use langchain-mcp-adapters' MultiServerMCPClient over
Streamable HTTP. Every request carries the service token, the user id and a
trace id (so one id follows a request through API -> graph -> MCP -> audit log).
"""

import asyncio
import os
import uuid
from datetime import timedelta
from typing import Any, ClassVar

from langchain_mcp_adapters.client import MultiServerMCPClient

from agent.marketplace_port import MarketplaceUnavailable
from agent.settings import mcp_url

# ---------------------------------------------------------------------------
# Which agent may use which tools (server -> tool names)
# ---------------------------------------------------------------------------
AGENT_TOOLS: dict[str, dict[str, list[str]]] = {
    "scout":          {"marketplace": ["search_jobs", "get_job"]},
    "job_analyst":    {},                                             # no tools: reads the job text only
    "risk_assessor":  {"marketplace": ["get_client_history", "get_policy"]},
    "fit_matcher":    {"portfolio": ["map_requirements", "search_evidence", "list_skills"]},
    "pricing":        {"marketplace": ["market_stats", "get_connects_balance", "get_policy"]},
    "writer":         {"portfolio": ["search_evidence", "get_case_study"]},
    "critic":         {"portfolio": ["search_evidence", "get_case_study"]},
    "compliance":     {},                                             # no tools: checks text against policy
    "submitter":      {"marketplace": ["create_proposal_draft", "submit_proposal"]},   # runs only after approval
    "client_liaison": {"marketplace": ["list_threads", "list_messages", "get_job", "send_message"],
                       "workspace": ["get_free_slots", "create_interview_hold", "create_email_draft"]},
    "pipeline":       {"marketplace": ["list_proposals", "list_threads"]},             # UI board refresh
}

TIMEOUT_S = 20
RETRIES = 2


class ToolNotAllowed(Exception):
    """An agent tried to use a tool outside its allowlist."""


class ToolCallError(Exception):
    """The tool ran but returned an error (bad input, refused by the marketplace...)."""


class ServerUnavailable(Exception):
    """A non-marketplace MCP server (portfolio/workspace) cannot be reached."""


class GigBidMCP:
    # Tests set this to {server_name: FastMCP} so every client runs in-memory (no HTTP).
    default_in_memory: ClassVar[dict] = {}

    def __init__(self, user_id: str, trace_id: str | None = None, in_memory: dict | None = None,
                 persona: str | None = None, account: str | None = None):
        """
        user_id   : whose data (sent as X-GigBid-User)
        trace_id  : one id for the whole run (sent as X-Trace-Id)
        in_memory : tests only - {server_name: FastMCP object} to call without HTTP
        """
        self.user_id = user_id
        self.persona = persona or user_id
        self.account = account or self.persona
        self.trace_id = trace_id or uuid.uuid4().hex
        self.in_memory = in_memory if in_memory is not None else GigBidMCP.default_in_memory
        headers = {"Authorization": f"Bearer {os.getenv('MCP_AUTH_TOKEN', '')}",
                   "X-GigBid-User": user_id, "X-GigBid-Persona": self.persona, "X-GigBid-Account": self.account,
                   "X-Trace-Id": self.trace_id}
        self.client = MultiServerMCPClient({
            name: {"transport": "streamable_http", "url": mcp_url(name), "headers": headers,
                   "timeout": timedelta(seconds=TIMEOUT_S)}
            for name in ("portfolio", "marketplace", "workspace")
        })

    @staticmethod
    def server_for(agent: str, tool: str) -> str:
        """Find which server provides `tool` for `agent`, or refuse."""
        for server, names in AGENT_TOOLS.get(agent, {}).items():
            if tool in names:
                return server
        raise ToolNotAllowed(f"agent '{agent}' is not allowed to use tool '{tool}'")

    async def _call_once(self, server: str, tool: str, args: dict):
        if server in self.in_memory:                     # unit tests: no network
            from mcp.shared.memory import create_connected_server_and_client_session

            from mcp_servers.common import IN_PROCESS_CALLER

            token = IN_PROCESS_CALLER.set({"user": self.user_id, "persona": self.persona,
                                             "account": self.account, "trace": self.trace_id})
            try:
                async with create_connected_server_and_client_session(self.in_memory[server]) as s:
                    return await s.call_tool(tool, args)
            finally:
                IN_PROCESS_CALLER.reset(token)
        async with self.client.session(server) as s:
            return await s.call_tool(tool, args)

    async def call(self, agent: str, tool: str, args: dict | None = None) -> Any:
        """
        Call one tool as `agent`. Returns the tool's structured output (dict or list).
        Polite pacing: if the server says RATE_LIMITED we wait and try again (up to ~1 minute)
        instead of failing - many jobs at once must slow down, not break.
        """
        for wait in (2, 4, 8, 15, 30, None):
            try:
                return await self._call(agent, tool, args)
            except ToolCallError as e:
                if "RATE_LIMITED" not in str(e) or wait is None:
                    raise
                await asyncio.sleep(wait)

    async def _call(self, agent: str, tool: str, args: dict | None = None) -> Any:
        server = self.server_for(agent, tool)
        last_error: Exception | None = None
        for attempt in range(RETRIES + 1):
            try:
                result = await asyncio.wait_for(self._call_once(server, tool, args or {}), TIMEOUT_S)
                break
            # Connection failures arrive as many different types (often wrapped in an
            # ExceptionGroup by the HTTP library), so we catch broadly here on purpose.
            except Exception as e:  # noqa: BLE001
                last_error = e
                if attempt < RETRIES:
                    await asyncio.sleep(0.5 * 2 ** attempt)
        else:
            if server == "marketplace":
                raise MarketplaceUnavailable(f"marketplace MCP server unreachable: {type(last_error).__name__}")
            raise ServerUnavailable(f"{server} MCP server unreachable: {type(last_error).__name__}")

        if result.isError:
            text = " ".join(getattr(c, "text", "") for c in result.content)
            if "MARKETPLACE_UNAVAILABLE" in text:
                raise MarketplaceUnavailable(text)
            raise ToolCallError(text)
        data = result.structuredContent
        # FastMCP wraps list outputs as {"result": [...]}; unwrap for convenience.
        if isinstance(data, dict) and set(data) == {"result"}:
            return data["result"]
        return data

    async def langchain_tools(self, agent: str):
        """The agent's allowed tools as LangChain tools (for LLM tool-calling, e.g. the ReAct baseline)."""
        allowed = {t for names in AGENT_TOOLS.get(agent, {}).values() for t in names}
        tools = []
        for server in AGENT_TOOLS.get(agent, {}):
            tools += [t for t in await self.client.get_tools(server_name=server) if t.name in allowed]
        return tools
