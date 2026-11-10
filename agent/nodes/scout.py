"""
Scout - runs saved searches, removes duplicates, and hands NEW jobs to the bid graph.

Not an LLM. Duplicate detection has two layers:
    1. same job id seen before
    2. same content (title + description fingerprint) seen before = a repost
Seen ids/fingerprints are stored in the LangGraph store, so a restart never
analyses the same job twice (idempotent processing).
Tools: marketplace search_jobs.
"""

import hashlib

from agent.mcp_client import GigBidMCP


def fingerprint(job: dict) -> str:
    text = (job["title"] + " " + job["description"]).lower()
    return hashlib.sha1(" ".join(text.split()).encode()).hexdigest()


async def scout(store, user_id: str, searches: list[dict], posted_after: str | None = None,
                persona: str | None = None, account: str | None = None) -> dict:
    """Returns {"new": [jobs], "duplicates": [job ids]}. `searches`: [{"query": "...", "category": "ml"}]."""
    mcp = GigBidMCP(user_id, persona=persona, account=account)
    new, dups = [], []
    for s in searches:
        jobs = await mcp.call("scout", "search_jobs", {"query": s.get("query", ""), "category": s.get("category"),
                                                       "posted_after": posted_after, "limit": 100})
        for job in jobs:
            if await store.aget(("scout_seen", user_id), job["job_id"]):
                continue                                           # already handled
            fp = fingerprint(job)
            original = await store.aget(("scout_fingerprints", user_id), fp)
            await store.aput(("scout_seen", user_id), job["job_id"], {"fingerprint": fp})
            if original:
                dups.append(job["job_id"])                         # repost of a job we already have
                continue
            await store.aput(("scout_fingerprints", user_id), fp, {"job_id": job["job_id"]})
            new.append(job)
    return {"new": new, "duplicates": dups}
