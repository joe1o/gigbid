"""
make_traces.py - produce the 3 public LangSmith traces the README links to.

    python scripts/make_traces.py        (needs GROQ_API_KEY and LANGSMITH_API_KEY in .env)

  1. a scam job that is skipped (no proposal is written)
  2. a good job: parallel analysis, Writer, claim check, Critic, Compliance, then a PAUSE for approval
  3. the same job after a "crash": the first runtime is closed, a NEW runtime on the same checkpoint
     database resumes the paused thread and submits once

Each trace is shared publicly (read-only link) and the links are saved to
evals/results/trace_links.json. Uses throwaway databases, so the live app is not touched.
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals.runners import harness

harness.setup(fake_llm=False, extra_env={"LANGSMITH_TRACING": "true"})

from langchain_core.tracers.context import collect_runs
from langchain_core.tracers.langchain import wait_for_all_tracers
from langsmith import Client

from agent import runtime as rt_mod

USER = "ml_engineer"
SETTINGS = rt_mod.default_settings(USER)


def job_of(kind: str) -> dict:
    jobs, labels = harness.load_dev(kinds=(kind,), personas=(USER,))
    lab = next(lab for lab in labels if lab.get("post_style", "detailed") == "detailed")
    return jobs[lab["job_id"]]


async def traced(step):
    """Run one graph call and return (snapshot, id of its root trace)."""
    with collect_runs() as cb:
        snap = await step()
    return snap, str(cb.traced_runs[0].id)


async def main():
    out = []
    scam, good = job_of("scam"), job_of("good")
    db = f"sqlite:///{harness.os.environ['DATABASE_URL'].removeprefix('sqlite:///')}"

    async with rt_mod.open_runtime(db) as rt:
        snap, rid = await traced(lambda: rt_mod.start_bid(rt, USER, scam, SETTINGS))
        out.append({"what": "scam job skipped before any writing", "job_id": scam["job_id"],
                    "status": snap["status"], "run_id": rid})
        snap, rid = await traced(lambda: rt_mod.start_bid(rt, USER, good, SETTINGS))
        out.append({"what": "good job: analysis, Writer, claim check, Critic, Compliance, paused for approval",
                    "job_id": good["job_id"], "status": snap["status"],
                    "critic_rounds": len(snap["values"].get("critiques", [])), "run_id": rid})
    # "crash": the runtime above is closed. A brand-new one on the same database resumes the thread.
    async with rt_mod.open_runtime(db) as rt2:
        snap, rid = await traced(lambda: rt_mod.resume_bid(rt2, USER, good["job_id"], {"action": "approve"}, SETTINGS))
        out.append({"what": "after a restart: new runtime resumes the paused thread, human approves, submitted once",
                    "job_id": good["job_id"], "status": snap["status"], "run_id": rid})

    wait_for_all_tracers()                       # make sure every trace reached LangSmith before sharing
    client = Client()
    for t in out:
        t["url"] = client.share_run(t["run_id"])      # public, read-only link
    harness.save("trace_links", {"traces": out})
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
