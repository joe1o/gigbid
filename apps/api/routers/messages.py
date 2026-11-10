"""messages.py - client conversations: list, open, draft a reply, approve/edit/reject."""

from fastapi import APIRouter, Depends, HTTPException

from agent import runtime as R
from apps.api import services as S
from apps.api.deps import get_rt, onboarded_user
from apps.api.routers.proposals import mcp_for
from apps.api.schemas.models import DecisionIn, Started, ThreadDetail, ThreadSummary

router = APIRouter(prefix="/api", tags=["messages"])


async def _title(rt, uid, thread_id) -> str:
    led = await rt.store.aget(("ledger", uid), thread_id)
    if not led:
        return ""
    j = await S.get_summary(rt.store, uid, led.value["job_id"])
    return j["title"] if j else led.value["job_id"]


@router.get("/threads", response_model=list[ThreadSummary])
async def threads(user=Depends(onboarded_user), rt=Depends(get_rt)):
    uid, out = user["user_id"], []
    for t in await mcp_for(user).call("pipeline", "list_threads"):
        if not await rt.store.aget(("ledger", uid), t["thread_id"]):
            continue
        st = await rt.store.aget(("conv_status", uid), t["thread_id"])
        out.append(ThreadSummary(thread_id=t["thread_id"], job_id=t["job_id"], job_title=await _title(rt, uid, t["thread_id"]),
                                 status=t["status"], last_message=t["last_message"], unanswered=t["unanswered"],
                                 draft_status=st.value["status"] if st else None))
    return out


@router.get("/threads/{thread_id}", response_model=ThreadDetail)
async def thread(thread_id: str, user=Depends(onboarded_user), rt=Depends(get_rt)):
    uid = user["user_id"]
    if not await rt.store.aget(("ledger", uid), thread_id):
        raise HTTPException(404, "conversation not found")
    msgs = await mcp_for(user).call("client_liaison", "list_messages", {"thread_id": thread_id})
    snap = await R.snapshot(rt.conv, R.run_config(R.conv_thread(uid, thread_id), user["settings"], "conversation"))
    return ThreadDetail(thread_id=thread_id, job_title=await _title(rt, uid, thread_id), messages=msgs,
                        status=snap["status"], approval=snap["interrupt"])


@router.post("/threads/{thread_id}/draft", response_model=Started)
async def draft_reply(thread_id: str, user=Depends(onboarded_user), rt=Depends(get_rt)):
    """Client Liaison reads the thread and drafts a reply (in the background) for your approval."""
    if not await rt.store.aget(("ledger", user["user_id"]), thread_id):
        raise HTTPException(404, "conversation not found")
    S.launch(S.run_conv(rt, user, thread_id))
    return Started(thread_id=R.conv_thread(user["user_id"], thread_id), status="drafting")


@router.post("/threads/{thread_id}/decision", response_model=Started)
async def decide(thread_id: str, body: DecisionIn, user=Depends(onboarded_user), rt=Depends(get_rt)):
    if body.action == "reject" and not (body.reason or "").strip():
        raise HTTPException(422, "please give a reason for rejecting")
    S.launch(S.run_conv(rt, user, thread_id, decision=body.model_dump()))
    return Started(thread_id=R.conv_thread(user["user_id"], thread_id), status="sending")
