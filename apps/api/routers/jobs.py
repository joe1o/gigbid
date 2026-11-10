"""jobs.py - the inbox and job detail: scout, list, open, skip, draft anyway, retry, history."""

from fastapi import APIRouter, Depends, HTTPException

from agent import runtime as R
from apps.api import services as S
from apps.api.deps import get_rt, onboarded_user
from apps.api.schemas.models import HistoryItem, JobDetail, JobSummary, ScoutOut, Started

router = APIRouter(prefix="/api", tags=["jobs"])


@router.post("/scout", response_model=ScoutOut)
async def scout(user=Depends(onboarded_user), rt=Depends(get_rt)):
    """Run the saved searches now. Each new job is analysed in the background."""
    return await S.scout_now(rt, user)


@router.get("/jobs", response_model=list[JobSummary])
async def list_jobs(status: str | None = None, category: str | None = None,
                    user=Depends(onboarded_user), rt=Depends(get_rt)):
    """The inbox: newest analysis first, best fit first, filtered by status/category."""
    rows = [i.value for i in await rt.store.asearch(("jobs", user["user_id"]), limit=1000)]
    if status:
        rows = [r for r in rows if r["status"] == status]
    if category:
        rows = [r for r in rows if r["category"] == category]
    rows.sort(key=lambda r: (r["status"] != "awaiting_approval", -(r.get("fit") or 0), -r["updated_at"]))
    return rows


async def _summary(rt, user, job_id) -> dict:
    s = await S.get_summary(rt.store, user["user_id"], job_id)
    if not s:
        raise HTTPException(404, "job not found")
    return s


@router.get("/jobs/{job_id}", response_model=JobDetail)
async def job_detail(job_id: str, user=Depends(onboarded_user), rt=Depends(get_rt)):
    """Everything about one job, including the pending approval (survives refreshes: it lives in the checkpointer)."""
    summary = await _summary(rt, user, job_id)
    snap = await R.snapshot(rt.bid, R.run_config(summary["thread_id"], user["settings"], "bid"))
    v = snap["values"] or {}
    keep = ["job_spec", "risk", "fit", "decision", "price", "draft", "claims", "critiques", "compliance",
            "marketplace_draft", "submission", "approval", "evidence", "error", "status"]
    return JobDetail(summary=summary, job=v.get("job", {}), state={k: v[k] for k in keep if k in v},
                     approval=snap["interrupt"], next=snap["next"])


@router.post("/jobs/{job_id}/skip", response_model=JobSummary)
async def skip(job_id: str, user=Depends(onboarded_user), rt=Depends(get_rt)):
    """The user files a job away (no tokens spent, nothing sent)."""
    s = await _summary(rt, user, job_id)
    s["status"] = "skipped"
    await S.save_summary(rt.store, user["user_id"], s)
    return s


async def _job(rt, user, summary) -> dict:
    snap = await R.snapshot(rt.bid, R.run_config(summary["thread_id"], user["settings"], "bid"))
    job = (snap["values"] or {}).get("job")
    if not job:
        raise HTTPException(409, "this job has no saved run yet")
    return job


@router.post("/jobs/{job_id}/draft", response_model=Started)
async def draft_anyway(job_id: str, user=Depends(onboarded_user), rt=Depends(get_rt)):
    """'Draft anyway' for a recommended skip/watch (never overrides a high-risk/scam verdict)."""
    s = await _summary(rt, user, job_id)
    job = await _job(rt, user, s)
    s["status"] = "analysing"
    await S.save_summary(rt.store, user["user_id"], s)
    S.launch(S.run_bid(rt, user, job, force=True))
    return Started(thread_id=s["thread_id"], status="analysing")


@router.post("/jobs/{job_id}/retry", response_model=Started)
async def retry(job_id: str, user=Depends(onboarded_user), rt=Depends(get_rt)):
    """Resume a queued/failed run from its last checkpoint."""
    s = await _summary(rt, user, job_id)
    S.launch(S.run_bid(rt, user, await _job(rt, user, s), mode="retry"))
    return Started(thread_id=s["thread_id"], status="analysing")


@router.get("/jobs/{job_id}/history", response_model=list[HistoryItem])
async def history(job_id: str, user=Depends(onboarded_user), rt=Depends(get_rt)):
    """Every checkpoint of this job's run (newest first) - replayable from any node."""
    s = await _summary(rt, user, job_id)
    return await R.history(rt, "bid", s["thread_id"])
