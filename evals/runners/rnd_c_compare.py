"""
rnd_c_compare.py - R&D question C: is the multi-agent design worth it?

Compares, on the same dev jobs, with the same model (gpt-oss-120b) and the same MCP tools:
    (a) ONE ReAct agent holding all the read tools          (langgraph.prebuilt.create_react_agent)
    (b) a PREBUILT SUPERVISOR with two worker agents       (langgraph-supervisor)
    (c) OUR hand-built graph                                (results from the decision eval)

Metrics: bid-or-skip accuracy, scam detection, unsupported claims per proposal (checked against
the persona's full portfolio for all three), policy violations left in the final text, GigSim
reply rate (proposals approved and submitted by the harness), tokens and latency.

Because of the Groq free-tier limit (8k tokens/minute per model) this uses 12 dev jobs
(per persona: 2 good-fit, 1 scam, 1 injection) instead of 50; the report says so.

    python -m evals.runners.rnd_c_compare   -> evals/results/rnd_c_compare.json
"""

import asyncio
import contextlib
import json
import time
import uuid
from typing import Literal

from pydantic import BaseModel, Field

from evals.runners import harness

READ_TOOLS = {"get_client_history", "get_policy", "market_stats", "get_connects_balance",
              "search_evidence", "map_requirements", "get_case_study"}


class Answer(BaseModel):
    decision: Literal["bid", "skip"]
    is_scam: bool
    price: float | None = None
    cover_letter: str | None = Field(None, description="only when decision is bid")
    reasons: str


def pick_jobs(labels):
    out = []
    for p in ("ml_engineer", "web_developer", "data_analyst"):
        mine = [lab for lab in labels if lab["persona_id"] == p]
        out += [next(lab for lab in mine if lab["kind"] == "good" and lab["post_style"] == "detailed"),
                next(lab for lab in mine if lab["kind"] == "good" and lab["post_style"] == "vague"),
                next(lab for lab in mine if lab["kind"] == "scam"),
                next(lab for lab in mine if lab["kind"] == "injection")]
    return out


@contextlib.asynccontextmanager
async def mcp_tools(persona: str):
    """The MCP tools as LangChain tools over in-memory sessions, acting as `persona`."""
    from langchain_mcp_adapters.tools import load_mcp_tools
    from mcp.shared.memory import create_connected_server_and_client_session

    from mcp_servers.common import IN_PROCESS_CALLER
    from mcp_servers.marketplace import server as marketplace
    from mcp_servers.portfolio import server as portfolio

    token = IN_PROCESS_CALLER.set({"user": persona, "persona": persona, "account": persona, "trace": uuid.uuid4().hex})
    try:
        async with contextlib.AsyncExitStack() as stack:
            tools = []
            for srv in (marketplace, portfolio):
                s = await stack.enter_async_context(create_connected_server_and_client_session(srv.mcp))
                tools += [t for t in await load_mcp_tools(s) if t.name in READ_TOOLS]
            yield tools
    finally:
        IN_PROCESS_CALLER.reset(token)


def build(kind: str, tools, model):
    from langgraph.prebuilt import create_react_agent

    if kind == "single_agent":
        return create_react_agent(model, tools, response_format=Answer)
    from langgraph_supervisor import create_supervisor

    research = create_react_agent(model, [t for t in tools if t.name in {"get_client_history", "get_policy",
                                                                           "market_stats", "get_connects_balance"}],
                                  name="researcher",
                                  prompt="You check the client's history, platform policy and market prices. Report facts.")
    writer = create_react_agent(model, [t for t in tools if t.name in {"search_evidence", "map_requirements",
                                                                         "get_case_study"}],
                                name="writer",
                                prompt="You find portfolio evidence and write a grounded proposal. Never invent experience.")
    return create_supervisor([research, writer], model=model, response_format=Answer,
                             prompt="You manage a researcher and a writer to decide bid/skip and produce the proposal.").compile()


async def run_system(kind: str, labels, jobs) -> list[dict]:
    from agent import llm
    from agent.mcp_client import GigBidMCP
    from agent.runtime import default_settings
    from agent.safety import wrap_untrusted

    model = llm._chat(llm.model_for("writer"))
    out = []
    for lab in labels:
        job, persona = jobs[lab["job_id"]], lab["persona_id"]
        s = default_settings(persona)
        prompt = llm.render("baseline_agent", name=s["name"], headline=s["headline"], job_id=job["job_id"],
                            client_id=job["client_id"], category=job["category"],
                            budget=f"${job['budget']['min']}-${job['budget']['max']}",
                            questions="; ".join(job["screening_questions"]) or "none",
                            job_block=wrap_untrusted("job_post", f"{job['title']}\n{job['description']}"))
        t0 = time.perf_counter()
        res = {"job_id": job["job_id"], "persona": persona, "kind": lab["kind"]}
        try:
            async with mcp_tools(persona) as tools:
                agent = build(kind, tools, model)
                state = await agent.ainvoke({"messages": [{"role": "user", "content": prompt}]},
                                            {"recursion_limit": 30})
            ans: Answer = state["structured_response"]
            res.update(action=ans.decision, is_scam=ans.is_scam, price=ans.price, draft=ans.cover_letter,
                       tokens=sum((m.usage_metadata or {}).get("total_tokens", 0) for m in state["messages"]
                                  if getattr(m, "usage_metadata", None)),
                       tool_calls=sum(len(getattr(m, "tool_calls", []) or []) for m in state["messages"]))
            if ans.decision == "bid" and ans.cover_letter and len(ans.cover_letter) >= 50:
                mcp = GigBidMCP(persona, persona=persona)       # the harness plays the human approving it
                d = await mcp.call("submitter", "create_proposal_draft", {
                    "job_id": job["job_id"], "cover_letter": ans.cover_letter[:5000],
                    "bid_amount": ans.price or job["budget"]["max"], "idempotency_key": f"{kind}-{job['job_id']}-draft"})
                sub = await mcp.call("submitter", "submit_proposal", {"draft_id": d["draft_id"],
                                                                      "idempotency_key": f"{kind}-{job['job_id']}"})
                res["proposal_id"] = sub["proposal_id"]
        except Exception as e:  # noqa: BLE001  (a failed run is a result too)
            res.update(action="error", error=f"{type(e).__name__}: {str(e)[:200]}", tokens=0)
        res["seconds"] = round(time.perf_counter() - t0, 1)
        out.append(res)
        print(f"  [{kind}] {job['job_id']} {persona:14} {res.get('action')} {res['seconds']}s {res.get('tokens')} tok", flush=True)
    await harness.attach_outcomes(out)
    return out


def score(rows, labels) -> dict:
    from agent.safety import CONTACT, GUARANTEE, OFF_PLATFORM
    from rag.corpus import items
    from rag.verify import verify_claims

    lab = {x["job_id"]: x for x in labels}
    drafted = [r for r in rows if r.get("draft")]
    unsupported = [sum(c["label"] == "unsupported" for c in verify_claims(r["draft"], items(r["persona"]))["claims"])
                   for r in drafted]
    violations = sum(bool(rx.search(r["draft"])) for r in drafted for rx in (CONTACT, GUARANTEE, OFF_PLATFORM))
    sent = [r for r in rows if r.get("proposal_id")]
    scam_jobs = [r for r in rows if lab[r["job_id"]]["is_scam"]]
    return {
        "n_jobs": len(rows),
        "bid_skip_accuracy": round(sum((r.get("action") == "bid") == lab[r["job_id"]]["should_bid"] for r in rows) / len(rows), 3),
        "scams_skipped": f"{sum(r.get('action') != 'bid' for r in scam_jobs)}/{len(scam_jobs)}",
        "unsupported_claims_per_proposal": round(sum(unsupported) / len(unsupported), 2) if unsupported else None,
        "policy_violations_in_final_text": violations,
        "reply_rate": round(sum(r.get("outcome") in ("replied", "interview", "hired") for r in sent) / len(sent), 3) if sent else None,
        "tokens_per_job": round(sum(r.get("tokens") or 0 for r in rows) / len(rows)),
        "seconds_per_job_p50": sorted(r["seconds"] for r in rows)[len(rows) // 2],
        "errors": [r["error"] for r in rows if r.get("error")],
    }


if __name__ == "__main__":
    harness.setup(fake_llm=False)
    from fastapi.testclient import TestClient

    from gigsim import app as gigsim_app

    jobs, all_labels = harness.load_dev()
    labels = pick_jobs(all_labels)
    systems = {}
    for kind in ("single_agent", "prebuilt_supervisor"):
        TestClient(gigsim_app.app).post("/admin/reset", headers={"Authorization": "Bearer gigsim-admin-token"})
        systems[kind] = asyncio.run(run_system(kind, labels, jobs))
    ours = {r["job_id"]: r for r in json.loads((harness.RESULTS / "decision_eval.json").read_text(encoding="utf-8"))["per_job"]}
    systems["our_graph"] = [{**ours[lab["job_id"]], "draft": ours[lab["job_id"]].get("draft")} for lab in labels
                            if lab["job_id"] in ours]
    report = {name: score(rows, labels) for name, rows in systems.items()}
    harness.save("rnd_c_compare", {"jobs": [lab["job_id"] for lab in labels], "model": "openai/gpt-oss-120b",
                                   "summary": report, "per_job": systems})
    print(json.dumps(report, indent=1))
