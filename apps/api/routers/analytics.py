"""analytics.py - analytics, the memory viewer and the marketplace health check."""

from collections import Counter

import numpy as np
from fastapi import APIRouter, Depends, HTTPException

from agent.memory import store as memory
from apps.api import services as S
from apps.api.deps import current_user, get_rt, onboarded_user
from apps.api.routers.proposals import mcp_for
from apps.api.schemas.models import Analytics, CategoryStats, CountRow, Health, MemoryItem

router = APIRouter(prefix="/api", tags=["analytics"])


@router.get("/analytics", response_model=Analytics)
async def analytics(user=Depends(onboarded_user), rt=Depends(get_rt)):
    uid = user["user_id"]
    jobs = [i.value for i in await rt.store.asearch(("jobs", uid), limit=1000)]
    props = []
    try:
        for p in await mcp_for(user).call("pipeline", "list_proposals"):
            led = await rt.store.aget(("ledger", uid), p["proposal_id"])
            if led:
                props.append({**p, "category": led.value["category"]})
    except Exception:  # noqa: BLE001, S110  (marketplace down: show what we have)
        pass

    by_cat = []
    for cat in sorted({p["category"] for p in props}):
        ps = [p for p in props if p["category"] == cat]
        replied = sum(p["status"] in ("replied", "interview", "hired") for p in ps)
        hired = sum(p["status"] == "hired" for p in ps)
        by_cat.append(CategoryStats(category=cat, sent=len(ps), replied=replied, hired=hired,
                                    reply_rate=round(replied / len(ps), 2), hire_rate=round(hired / len(ps), 2)))
    connects = Counter()
    for p in props:
        connects[p["status"]] += p["connects_spent"]

    analysed = [j for j in jobs if j.get("agent_seconds")]          # jobs the agents actually worked on
    drafted = [j for j in analysed if j["status"] in ("awaiting_approval", "submitted", "rejected")]
    secs = [j["agent_seconds"] for j in analysed] or [0]
    rejections = Counter(j["rejection_reason"] for j in jobs if j.get("rejection_reason"))
    skips = Counter((j["reasons"][2] if len(j.get("reasons", [])) > 2 else j.get("action") or "?").split(":")[0]
                    for j in jobs if j.get("action") in ("skip", "watch"))
    return Analytics(
        by_category=by_cat, connects_by_outcome=[CountRow(label=k, count=v) for k, v in connects.items()],
        proposals_analysed=len(analysed),
        avg_cost_usd_per_job=round(float(np.mean([j["cost_usd"] for j in analysed])) if analysed else 0.0, 6),
        avg_cost_usd_per_proposal=round(float(np.mean([j["cost_usd"] for j in drafted])) if drafted else 0.0, 6),
        p50_seconds_per_job=round(float(np.percentile(secs, 50)), 2),
        p95_seconds_per_job=round(float(np.percentile(secs, 95)), 2),
        rejection_reasons=[CountRow(label=k, count=v) for k, v in rejections.most_common(8)],
        skip_reasons=[CountRow(label=k, count=v) for k, v in skips.most_common(8)])


@router.get("/memory", response_model=list[MemoryItem])
async def memories(user=Depends(current_user), rt=Depends(get_rt)):
    """Everything GigBid has learned about you (promoted memories only)."""
    out = []
    for m in await memory.list_memories(rt.store, user["user_id"]):
        out.append(MemoryItem(namespace=m["namespace"].replace("/", "~"), key=m["key"], rule=m.get("rule"),
                              value={k: v for k, v in m.items() if k not in ("namespace", "key")}))
    return out


@router.delete("/memory/{namespace}/{key}")
async def forget(namespace: str, key: str, user=Depends(current_user), rt=Depends(get_rt)) -> dict:
    if not (namespace == "style" or namespace.startswith("outcome")):
        raise HTTPException(404, "unknown memory")
    await memory.delete_memory(rt.store, user["user_id"], namespace.replace("~", "/"), key)
    return {"deleted": True}


@router.get("/health", response_model=Health)
async def health(user=Depends(current_user), rt=Depends(get_rt)):
    h = await S.marketplace_health()
    queued = sum(i.value["status"] == "queued" for i in await rt.store.asearch(("jobs", user["user_id"]), limit=1000))
    return Health(marketplace="ok" if h["ok"] else "down", detail=h["detail"], queued_jobs=queued)
