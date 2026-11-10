"""
Client Liaison - reads client replies, drafts an answer, and waits for approval.

Steps (nodes of the conversation graph):
    load_thread   read the conversation (marketplace list_messages) + the job
    classify      rules first (off-platform = scam signal), then the small LLM picks the intent
    plan_reply    RULES decide what to do (never the client's text):
                     question -> answer from the proposal's facts
                     negotiation -> accept if at/above the user's floor, else counter at the floor
                     interview request -> offer free calendar slots (workspace get_free_slots)
                     scam signal -> politely refuse to leave the platform
    draft_reply   the strong LLM writes the message following that instruction
    compliance    remove contact details / guarantees / off-platform talk
    approval      interrupt(): the human approves, edits or rejects
    send          send_message + tentative calendar holds for the offered slots (idempotent keys)
"""

from langgraph.config import get_store
from langgraph.types import interrupt

from agent import llm
from agent.handoffs import ApprovalDecision, ComplianceVerdict, IntentOut
from agent.memory import store as memory
from agent.nodes.base import configurable, node, tools, user_settings
from agent.nodes.compliance import scan
from agent.safety import OFF_PLATFORM, find_injections, wrap_untrusted


@node("load_thread")
async def load_thread(state, config):
    t = tools(state, config)
    msgs = await t.call("client_liaison", "list_messages", {"thread_id": state["thread_id"]})
    if not msgs or msgs[-1]["sender"] != "client":
        return {"messages": msgs, "status": "nothing_to_do"}
    return {"messages": msgs, "last_client_message": msgs[-1], "status": "running"}


@node("classify")
async def classify(state, config):
    text = state["last_client_message"]["text"]
    injections = find_injections(text)
    if OFF_PLATFORM.search(text):                       # rules win: no model needed
        return {"intent": {"intent": "scam_signal", "summary": "asks to move off the platform",
                           "offered_amount": None, "injections": injections}}
    out, usage = await llm.structured("liaison_intent", "liaison_intent", IntentOut,
                                      message_block=wrap_untrusted("client_message", text))
    return {"intent": {**out.model_dump(), "injections": injections}, "usage": [usage]}


@node("plan_reply")
async def plan_reply(state, config):
    intent = state["intent"]
    s = user_settings(config)
    floor = s.get("fixed_floor_usd", 0)
    slots = []
    kind = intent["intent"]
    if kind == "interview_request":
        slots = await tools(state, config).call("client_liaison", "get_free_slots", {"max_slots": 3})
        instruction = ("Thank them and propose exactly these times (the freelancer's timezone, UTC+5): "
                       + "; ".join(x["label"] for x in slots) + ". Ask which one works.")
    elif kind == "negotiation":
        offer = intent.get("offered_amount") or 0
        if offer >= floor:
            instruction = f"Accept the price of ${offer:.0f} politely and confirm the next step."
        else:
            instruction = (f"Politely explain that ${floor:.0f} is the lowest price that covers the work well; "
                           f"offer ${floor:.0f}, or a smaller scope for less.")
    elif kind == "scam_signal":
        instruction = ("Politely say that all communication and payment must stay on the platform, as its rules "
                       "require, and that you are happy to continue here. Do not share any contact details.")
    elif kind == "interview_confirmed":
        instruction = "Confirm the agreed time and say you look forward to the call."
    elif kind == "question":
        instruction = ("Answer the question in 2-4 sentences using only facts from the proposal, then offer a "
                       "short call.")
    else:
        instruction = "Thank the client briefly and ask how they would like to proceed."
    return {"slots": slots, "intent": {**intent, "instruction": instruction}}


@node("draft_reply")
async def draft_reply(state, config):
    store = get_store()
    led = None
    if store:
        led = await store.aget(("ledger", state["user_id"]), state["thread_id"])
    convo = "\n".join(f"{m['sender'].upper()}: {m['text']}" for m in state["messages"][-8:])
    reply, usage = await llm.text("liaison_reply", "liaison_reply",
                                  name=user_settings(config).get("name", "the freelancer"),
                                  instruction=state["intent"]["instruction"],
                                  proposal=led.value["cover_letter"] if led else "(not available)",
                                  conversation_block=wrap_untrusted("conversation", convo))
    return {"reply": reply.strip(), "usage": [usage]}


@node("reply_compliance")
async def reply_compliance(state, config):
    text, fixes = scan(state["reply"])
    blocked = None if len(text.split()) >= 5 else "nothing left to send after removing policy violations"
    out = {"reply": text, "compliance": ComplianceVerdict(passed=blocked is None, fixes=fixes,
                                                          blocked_reason=blocked).model_dump()}
    if blocked:
        out["status"] = "blocked"
    return out


@node("prepare_reply_approval")
async def prepare_reply_approval(state, config):
    preview = await tools(state, config).call("client_liaison", "send_message", {
        "thread_id": state["thread_id"], "text": state["reply"], "idempotency_key": "preview-only", "dry_run": True})
    return {"status": "awaiting_approval", "approval": {"preview": preview}}


@node("reply_approval", attempts=1, timeout=None)
async def reply_approval(state, config):
    answer = ApprovalDecision(**interrupt({
        "kind": "message", "thread_id": state["thread_id"], "messages": state["messages"],
        "intent": state["intent"], "reply": state["reply"], "slots": state.get("slots", []),
        "compliance": state.get("compliance"), "preview": state["approval"].get("preview")}))
    if answer.action == "reject":
        return {"approval": answer.model_dump(), "status": "rejected"}
    if answer.action == "edit" and answer.cover_letter:
        store = get_store()
        if store:
            edit_id = f"{configurable(config)['thread_id']}:{state['last_client_message']['id']}"
            await memory.record_edit(store, state["user_id"], edit_id, state["reply"], answer.cover_letter)
        text, fixes = scan(answer.cover_letter)
        return {"approval": answer.model_dump(), "reply": text,
                "compliance": ComplianceVerdict(passed=not fixes, violations=fixes).model_dump(), "status": "running"}
    return {"approval": answer.model_dump(), "status": "running"}


def after_reply_approval(state) -> str:
    a = state["approval"]["action"]
    if a == "reject":
        return "__end__"
    if a == "edit":
        return "prepare_reply_approval"      # show the edited text (and any violations) once more
    return "send"


@node("send")
async def send(state, config):
    t = tools(state, config)
    key = f"{state['thread_id']}:{state['last_client_message']['id']}"
    res = await t.call("client_liaison", "send_message", {"thread_id": state["thread_id"], "text": state["reply"],
                                                          "idempotency_key": key})
    holds = []
    for slot in state.get("slots", []):          # tentative holds so the times stay free
        holds.append(await t.call("client_liaison", "create_interview_hold", {
            "start": slot["start"], "title": f"Interview (thread {state['thread_id']})",
            "idempotency_key": f"{key}:hold:{slot['start']}"}))
    return {"sent": {**res, "holds": holds}, "status": "sent"}
