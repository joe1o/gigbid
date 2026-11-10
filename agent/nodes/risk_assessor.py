"""
Risk Assessor - is this client/job safe to bid on?

Two layers:
  1. RULES (free, explainable) on the client's history and the post's text:
     unverified payment, no spend, brand-new account, tiny budget, free-work requests,
     off-platform contact or payment, injected instructions.
  2. A small LLM's second opinion (gpt-oss-20b) for scams the rules miss.
Final score = max(rule score, 0.75 if the LLM says scam). Level: high >= 0.7, medium >= 0.4.

Tools: marketplace get_client_history, get_policy (read only).
"""

import json

from agent import llm
from agent.handoffs import RiskOpinion, RiskReport
from agent.nodes.base import node, tools
from agent.safety import FREE_WORK, OFF_PLATFORM, find_injections, wrap_untrusted


def rule_score(job: dict, client: dict) -> tuple[float, list[str], list[str]]:
    """Returns (score, flags, human-readable reasons)."""
    score, flags, reasons = 0.0, [], []
    text = f"{job['title']} {job['description']}"

    def add(points, flag, reason):
        nonlocal score
        score += points
        flags.append(flag)
        reasons.append(reason)

    if not client.get("payment_verified"):
        add(0.25, "payment_unverified", "client payment method is not verified")
    if client.get("total_spent_usd", 0) == 0:
        add(0.15, "no_spend_history", "client has never paid anyone")
    if client.get("account_age_days", 999) < 30:
        add(0.2, "new_account", f"account is {client.get('account_age_days')} days old")
    if job["budget"]["max"] < 100:
        add(0.15, "tiny_budget", f"budget only ${job['budget']['max']:.0f}")
    if FREE_WORK.search(text):
        add(0.35, "free_work_request", "asks for unpaid work as a 'test'")
    if OFF_PLATFORM.search(text):
        add(0.35, "off_platform", "asks to move contact or payment off the platform")
    if find_injections(job["description"]):
        add(0.1, "injected_instructions", "post contains text that tries to instruct an AI")
    return min(score, 1.0), flags, reasons


@node("risk_assessor")
async def risk_assessor(state, config):
    job = state["job"]
    t = tools(state, config)
    client = await t.call("risk_assessor", "get_client_history", {"client_id": job["client_id"]})
    policy = await t.call("risk_assessor", "get_policy")
    score, flags, reasons = rule_score(job, client)

    opinion, usage = await llm.structured(
        "risk_assessor", "risk_assessor", RiskOpinion,
        client=json.dumps(client), policy="\n".join(f"- {r}" for r in policy["rules"]),
        job_block=wrap_untrusted("job_post", f"{job['title']}\n{job['description']}"))
    if opinion.is_scam:
        score = max(score, 0.75)
        flags.append("llm_scam_opinion")
    level = "high" if score >= 0.7 else "medium" if score >= 0.4 else "low"
    report = RiskReport(score=round(score, 2), level=level, flags=flags,
                        explanation="; ".join(reasons) + (f". Model: {opinion.explanation}" if opinion.explanation else ""),
                        client=client)
    return {"risk": report.model_dump(), "usage": [usage]}
