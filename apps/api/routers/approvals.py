"""
approvals.py - the human decision on a proposal, and "regenerate one paragraph".

POST /decision resumes the PAUSED graph thread (LangGraph Command(resume=...)) in the
background. Because the pause lives in the checkpointer, it works after a page refresh
or a server restart.
"""

import asyncio
import re

from fastapi import APIRouter, Depends, HTTPException

from agent import llm
from agent import runtime as R
from agent.nodes.writer import evidence_block
from apps.api import services as S
from apps.api.deps import get_rt, onboarded_user
from apps.api.schemas.models import DecisionIn, RegenerateIn, RegenerateOut, Started
from rag.verify import verify_claims

router = APIRouter(prefix="/api", tags=["approvals"])


async def _paused(rt, user, job_id):
    s = await S.get_summary(rt.store, user["user_id"], job_id)
    if not s:
        raise HTTPException(404, "job not found")
    snap = await R.snapshot(rt.bid, R.run_config(s["thread_id"], user["settings"], "bid"))
    return s, snap


@router.post("/jobs/{job_id}/decision", response_model=Started)
async def decide(job_id: str, body: DecisionIn, user=Depends(onboarded_user), rt=Depends(get_rt)):
    """Approve (send), edit (save + re-check, then approve again) or reject with a reason."""
    s, snap = await _paused(rt, user, job_id)
    if not snap["interrupt"]:
        raise HTTPException(409, f"nothing is waiting for approval (status: {snap['status']})")
    if body.action == "reject" and not (body.reason or "").strip():
        raise HTTPException(422, "please give a reason for rejecting")
    if body.action == "edit" and not (body.cover_letter or "").strip():
        raise HTTPException(422, "the edited cover letter is empty")
    s["status"] = "analysing"
    await S.save_summary(rt.store, user["user_id"], s)
    S.launch(S.run_bid(rt, user, snap["values"]["job"], mode="resume", decision=body.model_dump()))
    return Started(thread_id=s["thread_id"], status="analysing")


@router.post("/jobs/{job_id}/regenerate", response_model=RegenerateOut)
async def regenerate(job_id: str, body: RegenerateIn, user=Depends(onboarded_user), rt=Depends(get_rt)):
    """Rewrite ONE paragraph with the Writer's model, grounded in the same evidence, then verify it.
    The new text is only a suggestion in the editor; it is sent only through edit + approve."""
    _, snap = await _paused(rt, user, job_id)
    v = snap["values"]
    paragraphs = [p for p in re.split(r"\n\s*\n", v["draft"]["cover_letter"]) if p.strip()]
    if body.paragraph_index >= len(paragraphs):
        raise HTTPException(422, f"the letter has {len(paragraphs)} paragraph(s)")
    text, _usage = await llm.text("writer", "regenerate_paragraph", name=user["settings"].get("name", ""),
                                  instruction=body.instruction or "make it more specific to the client",
                                  summary=v["job_spec"]["summary"], letter=v["draft"]["cover_letter"],
                                  paragraph=paragraphs[body.paragraph_index], evidence=evidence_block(v["evidence"]))
    checked = await asyncio.to_thread(verify_claims, text, v["evidence"])                  # unsupported claims are dropped here too
    return RegenerateOut(paragraph=checked["cleaned_draft"], claims=checked["claims"])
