"""
Approval + submission (requirements R4, C5, C6).

prepare_approval : saves the proposal as a DRAFT on the marketplace server and gets the
                   dry-run preview (exact payload + Connects cost). Nothing is sent.
approval         : PAUSES the graph with interrupt(). The UI shows the payload; the human
                   answers approve / edit / reject. The pause is saved in the checkpointer,
                   so it survives restarts and page refreshes.
submit           : submits the approved draft. The idempotency key is derived from the
                   thread and draft id, so even if the app crashes mid-submit and the step
                   re-runs, the marketplace submits (and charges Connects) EXACTLY ONCE.
"""

import hashlib

from langgraph.config import get_store
from langgraph.types import interrupt

from agent.handoffs import ApprovalDecision
from agent.memory import store as memory
from agent.nodes.base import configurable, node, tools


@node("prepare_approval")
async def prepare_approval(state, config):
    d, thread = state["draft"], configurable(config)["thread_id"]
    text_hash = hashlib.sha1((d["cover_letter"] + "|".join(d["screening_answers"])).encode()).hexdigest()[:10]
    md = await tools(state, config).call("submitter", "create_proposal_draft", {
        "job_id": state["job"]["job_id"], "cover_letter": d["cover_letter"], "bid_amount": state["price"]["amount"],
        "screening_answers": d["screening_answers"], "idempotency_key": f"{thread}:draft:{text_hash}"})
    return {"marketplace_draft": md, "status": "awaiting_approval"}


def approval_payload(state) -> dict:
    """Everything the human needs to decide, in one object."""
    return {
        "kind": "proposal",
        "job": {k: state["job"][k] for k in ("job_id", "title", "budget", "client_id", "connects_cost")},
        "draft": state["draft"],
        "claims": state["claims"]["claims"],               # evidence id behind every claim (hover in the UI)
        "evidence": [{k: e[k] for k in ("id", "type", "title", "text")} for e in state["evidence"]],
        "risk": state["risk"], "fit": state["fit"], "price": state["price"],
        "critiques": state.get("critiques", []), "compliance": state.get("compliance"),
        "preview": state["marketplace_draft"]["preview"],   # dry-run: what will be sent + cost
    }


@node("approval", attempts=1, timeout=None)
async def approval(state, config):
    answer = ApprovalDecision(**interrupt(approval_payload(state)))   # <-- the graph pauses here
    if answer.action == "reject":
        return {"approval": answer.model_dump(), "status": "rejected"}
    if answer.action == "edit":
        old = state["draft"]
        new = {**old, "cover_letter": answer.cover_letter or old["cover_letter"],
               "screening_answers": answer.screening_answers or old["screening_answers"],
               "version": old["version"] + 1, "edited_by_user": True}
        store = get_store()
        if store:  # learn from the edit (only promoted after the rule allows it)
            edit_id = f"{configurable(config)['thread_id']}:v{old['version']}"
            await memory.record_edit(store, state["user_id"], edit_id, old["cover_letter"], new["cover_letter"])
        return {"approval": answer.model_dump(), "draft": new, "status": "running"}
    return {"approval": answer.model_dump(), "status": "running"}


def after_approval(state) -> str:
    action = state["approval"]["action"]
    return {"reject": "__end__", "edit": "compliance_edit"}.get(action, "submit")


@node("submit")
async def submit(state, config):
    md, thread = state["marketplace_draft"], configurable(config)["thread_id"]
    res = await tools(state, config).call("submitter", "submit_proposal", {
        "draft_id": md["draft_id"], "idempotency_key": f"{thread}:submit:{md['draft_id']}"})
    store = get_store()
    if store:  # bookkeeping so outcomes can later be matched to this proposal
        await store.aput(("ledger", state["user_id"]), res["proposal_id"], {
            "job_id": state["job"]["job_id"], "category": state["job"]["category"],
            "cover_letter": state["draft"]["cover_letter"], "thread_id": thread})
    return {"submission": res, "status": "submitted"}
