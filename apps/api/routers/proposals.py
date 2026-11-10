"""proposals.py - the pipeline board (kanban), kept current from marketplace events."""

from fastapi import APIRouter, Depends

from agent.mcp_client import GigBidMCP
from agent.memory import store as memory
from apps.api.deps import get_rt, onboarded_user
from apps.api.schemas.models import PipelineCard, PipelineOut

router = APIRouter(prefix="/api", tags=["proposals"])
COLUMNS = ["drafted", "submitted", "viewed", "replied", "interview", "hired", "lost"]


def mcp_for(user: dict) -> GigBidMCP:
    s = user["settings"]
    return GigBidMCP(user["user_id"], persona=s.get("persona"), account=s.get("account"))


@router.get("/pipeline", response_model=PipelineOut)
async def pipeline(user=Depends(onboarded_user), rt=Depends(get_rt)):
    uid = user["user_id"]
    cols: dict[str, list[PipelineCard]] = {c: [] for c in COLUMNS}
    jobs = {i.key: i.value for i in await rt.store.asearch(("jobs", uid), limit=1000)}
    for j in jobs.values():                                   # drafts waiting for the user
        if j["status"] == "awaiting_approval":
            cols["drafted"].append(PipelineCard(job_id=j["job_id"], title=j["title"], category=j["category"],
                                                status="drafted", bid_amount=j.get("price")))
    mcp = mcp_for(user)
    for p in await mcp.call("pipeline", "list_proposals"):     # live statuses from the marketplace
        led = await rt.store.aget(("ledger", uid), p["proposal_id"])
        if not led:
            continue                                          # another user's proposal on a shared account
        j = jobs.get(led.value["job_id"], {})
        cols.setdefault(p["status"], []).append(PipelineCard(
            job_id=led.value["job_id"], title=j.get("title", led.value["job_id"]), category=led.value["category"],
            status=p["status"], proposal_id=p["proposal_id"], bid_amount=p["bid_amount"],
            connects_spent=p["connects_spent"]))
    await memory.sync_outcomes(rt.store, uid, mcp)              # outcomes feed outcome memory (via its rule)
    return PipelineOut(columns=cols)
