"""
streaming.py - live progress from LangGraph to the browser (Server-Sent Events).

In simple words:
    While a graph runs in the background, every node that finishes produces an
    "update" (LangGraph stream_mode="updates"). We turn each one into a small event
    ("risk_assessor finished: risk high") and push it to everyone watching that run.
    The browser listens with EventSource, so the user sees the run step by step instead
    of staring at a spinner.

    SSE = Server-Sent Events: a long-lived HTTP response the server keeps writing lines to.
    Events are also kept in memory per thread, so a page opened mid-run catches up.
    After a restart, the full step history still comes from the checkpointer.
"""

import asyncio
import json
import time
from collections import defaultdict

NODE_LABELS = {
    "intake": "Job received", "job_analyst": "Job Analyst extracted the spec", "risk_assessor": "Risk Assessor scored the client",
    "fit_matcher": "Fit Matcher mapped requirements to evidence", "decide": "Decision made", "pricing": "Pricing Strategist set a price",
    "writer": "Writer drafted the proposal", "verify_claims": "Claims checked against evidence", "critic": "Critic reviewed the draft",
    "compliance": "Compliance Guard checked the policy", "prepare_approval": "Draft saved, dry-run preview ready",
    "approval": "Your decision recorded", "compliance_edit": "Your edits re-checked", "submit": "Proposal submitted",
    "needs_attention": "Budget exceeded", "load_thread": "Conversation loaded", "classify": "Message classified",
    "plan_reply": "Reply planned", "draft_reply": "Reply drafted", "reply_compliance": "Reply checked",
    "prepare_reply_approval": "Reply ready for approval", "reply_approval": "Your decision recorded", "send": "Message sent",
}


def describe(node: str, out: dict) -> str:
    """One short human sentence about what a node produced."""
    if not isinstance(out, dict):
        return ""
    if node == "risk_assessor" and "risk" in out:
        r = out["risk"]
        return f"risk {r['level']} ({r['score']}) {', '.join(r['flags'][:3])}"
    if node == "fit_matcher" and "fit" in out:
        return f"fit {out['fit']['score']} - " + "; ".join(out["fit"]["reasons"][:1])
    if node == "decide" and "decision" in out:
        return f"{out['decision']['action']}: " + "; ".join(out["decision"]["reasons"][2:3])
    if node == "pricing" and "price" in out:
        return f"${out['price']['amount']:.0f}, {out['price']['connects_cost']} Connects"
    if node == "critic" and out.get("critiques"):
        c = out["critiques"][-1]
        return "approved" if c["approved"] else "sent back: " + "; ".join(c["issues"][:2])
    if node == "verify_claims" and "claims" in out:
        cl = out["claims"]["claims"]
        return f"{sum(c['label'] == 'supported' for c in cl)}/{len(cl)} claims supported, {len(out['claims']['removed'])} removed"
    if node == "compliance" and "compliance" in out:
        c = out["compliance"]
        return c["blocked_reason"] or (f"{len(c['fixes'])} fix(es)" if c["fixes"] else "passed")
    if out.get("error"):
        return out["error"]
    return out.get("status", "") or ""


class RunHub:
    def __init__(self):
        self.events: dict[str, list[dict]] = defaultdict(list)
        self.subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)

    def publish(self, thread_id: str, event: dict) -> None:
        event = {"ts": time.time(), **event}
        log = self.events[thread_id]
        log.append(event)
        del log[:-300]                                   # keep the last 300 events per thread
        for q in list(self.subscribers[thread_id]):
            q.put_nowait(event)

    def on_update(self, thread_id: str):
        """A callback for agent.runtime._run: turns LangGraph updates into events."""
        async def handle(update: dict):
            for node, out in update.items():
                if node == "__interrupt__":
                    self.publish(thread_id, {"type": "interrupt", "node": "approval",
                                             "label": "Waiting for your approval"})
                    continue
                usage = out.get("usage", []) if isinstance(out, dict) else []
                self.publish(thread_id, {
                    "type": "node", "node": node, "label": NODE_LABELS.get(node, node), "detail": describe(node, out),
                    "status": out.get("status") if isinstance(out, dict) else None,
                    "tokens": sum(u["input_tokens"] + u["output_tokens"] for u in usage),
                    "cost_usd": sum(u["cost_usd"] for u in usage)})
        return handle

    async def stream(self, thread_id: str):
        """Yield SSE messages: first everything so far, then new events until the run ends."""
        q: asyncio.Queue = asyncio.Queue()
        self.subscribers[thread_id].add(q)
        try:
            for e in list(self.events[thread_id]):
                yield {"data": json.dumps(e)}
            while True:
                try:
                    e = await asyncio.wait_for(q.get(), timeout=20)
                except TimeoutError:
                    yield {"event": "ping", "data": "{}"}      # keeps the connection open
                    continue
                yield {"data": json.dumps(e)}
        finally:
            self.subscribers[thread_id].discard(q)


hub = RunHub()
