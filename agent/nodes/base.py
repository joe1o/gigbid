"""
base.py - things every agent node shares (requirements C4 and C7).

    @node("name")  wraps a node function with:
        - a per-node TIMEOUT and RETRIES (try again once after a short wait)
        - DEAD-LETTER: if it still fails, the job is parked with status "dead_letter"
          and the error, instead of crashing the whole app
        - a STEP counter (for the step budget)
        - "marketplace down" is NOT dead-lettered: it is re-raised so the job pauses at
          this node and can be resumed later from the checkpoint (degraded mode)

    guard(next)  is used on every edge: it stops the graph when the job reached a final
    status, and sends it to "needs_attention" when the step or token budget is used up.
"""

import asyncio
import functools

from langgraph.errors import GraphBubbleUp
from langgraph.graph import END

from agent.marketplace_port import MarketplaceUnavailable
from agent.mcp_client import GigBidMCP
from agent.settings import CONFIG

# Statuses after which the graph stops.
STOP = {"skipped", "recommended_skip", "watch", "blocked", "rejected", "submitted", "needs_attention",
        "dead_letter", "nothing_to_do", "sent"}
NODE_TIMEOUT_S = 150
BUDGET = CONFIG["budgets"]


def configurable(config) -> dict:
    return (config or {}).get("configurable", {})


def user_settings(config) -> dict:
    """Per-user settings (name, rate floor, autonomy...) passed in when the run starts."""
    return configurable(config).get("settings", {})


def tools(state, config) -> GigBidMCP:
    """An MCP client for this user; the thread id doubles as the trace id."""
    return GigBidMCP(state["user_id"], trace_id=configurable(config).get("thread_id"))


def node(name: str, attempts: int = 2, timeout: float | None = NODE_TIMEOUT_S):
    def deco(fn):
        @functools.wraps(fn)
        async def wrapped(state, config):
            if state.get("status") in STOP:          # job already finished (e.g. a parallel branch failed)
                return {}
            last = None
            for attempt in range(attempts):
                try:
                    coro = fn(state, config)
                    out = (await asyncio.wait_for(coro, timeout) if timeout else await coro) or {}
                    out["steps"] = out.get("steps", 0) + 1
                    return out
                except (GraphBubbleUp, MarketplaceUnavailable):
                    raise                            # human-approval pause / degraded mode: not an error
                except Exception as e:  # noqa: BLE001
                    last = e
                    if attempt < attempts - 1:
                        await asyncio.sleep(1.5)
            return {"status": "dead_letter", "error": f"{name}: {type(last).__name__}: {last}", "steps": 1}
        wrapped.node_name = name
        return wrapped
    return deco


def tokens_used(state) -> int:
    return sum(u.get("input_tokens", 0) + u.get("output_tokens", 0) for u in state.get("usage", []))


def over_budget(state) -> bool:
    return state.get("steps", 0) >= BUDGET["max_graph_steps"] or tokens_used(state) >= BUDGET["max_tokens_per_job"]


def guard(next_node: str):
    """Edge router: stop if finished, divert if over budget, otherwise continue to next_node."""
    def route(state):
        if state.get("status") in STOP:
            return END
        if over_budget(state):
            return "needs_attention"
        return next_node
    route.__name__ = f"to_{next_node}"
    return route


async def needs_attention(state, config):
    """Budget exceeded: park the job where the user can see it."""
    return {"status": "needs_attention",
            "error": f"budget exceeded: {state.get('steps', 0)} steps, {tokens_used(state)} tokens"}
