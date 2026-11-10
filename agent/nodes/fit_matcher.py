"""
Fit Matcher - maps every requirement to portfolio evidence and scores the fit.

No LLM: it asks the Portfolio MCP server's `map_requirements` tool, which uses the
corrective retrieval design (V8). A requirement with no trustworthy evidence comes
back as "none", so it lowers the fit score and the Writer will not claim it.

fit score = (requirements with evidence) / (all requirements)

It runs in parallel with the Job Analyst, so it uses the skills the client listed
on the marketplace (it cannot wait for the analyst's output).
"""

from agent.handoffs import FitReport
from agent.nodes.base import node, tools


@node("fit_matcher")
async def fit_matcher(state, config):
    job = state["job"]
    requirements = job["required_skills"] or [job["title"]]
    rows = await tools(state, config).call("fit_matcher", "map_requirements",
                                           {"requirements": requirements, "job_title": job["title"]})
    matched = [r["requirement"] for r in rows if r["status"] == "found"]
    missing = [r["requirement"] for r in rows if r["status"] == "none"]
    score = len(matched) / len(rows) if rows else 0.0
    report = FitReport(score=round(score, 2), matrix=rows, matched=matched, missing=missing,
                       reasons=[f"{len(matched)} of {len(rows)} requirements have portfolio evidence"]
                       + ([f"no evidence for: {', '.join(missing)}"] if missing else []))
    return {"fit": report.model_dump()}
