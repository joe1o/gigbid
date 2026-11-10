"""
Critic - checks grounding, personalisation, length and screening answers.
Can send the draft back to the Writer AT MOST twice (budgets.max_revisions).

Two layers:
  1. Hard checks in code (always the same answer): length range, generic opening,
     unanswered screening questions, claims that were removed by verification.
  2. The strong LLM (gpt-oss-120b) judges personalisation and overall quality.
Approved only if the LLM approves AND there are no hard-check failures.
"""

from agent import llm
from agent.handoffs import Critique, CritiqueLLM
from agent.nodes.base import node
from agent.nodes.writer import evidence_block
from agent.safety import GENERIC_OPENINGS
from agent.settings import CONFIG

MAX_REV = CONFIG["budgets"]["max_revisions"]
WORDS = CONFIG["thresholds"]["proposal_words"]


def hard_checks(state) -> list[str]:
    d, spec, claims = state["draft"], state["job_spec"], state["claims"]
    issues = []
    n = len(d["cover_letter"].split())
    if n < WORDS[0] * 0.8 or n > WORDS[1] * 1.2:
        issues.append(f"length is {n} words; aim for {WORDS[0]}-{WORDS[1]}")
    first = d["cover_letter"].strip().lower()[:80]
    if any(g in first for g in GENERIC_OPENINGS):
        issues.append("generic opening: start with the client's problem")
    unanswered = len(spec["screening_questions"]) - sum(bool(a.strip()) for a in d["screening_answers"])
    if unanswered > 0:
        issues.append(f"{unanswered} screening question(s) not answered")
    if claims["removed"]:
        issues.append(f"{len(claims['removed'])} unsupported claim(s) were removed; only claim what the evidence shows")
    return issues


@node("critic")
async def critic(state, config):
    rnd = state.get("revisions", 0)
    hard = hard_checks(state)
    checks = "\n".join(f"- {c['label']}: {c['text']}" for c in state["claims"]["claims"]) or "- no claims found"
    checks += "\n" + ("\n".join(f"- FAILED: {h}" for h in hard) if hard else "- all hard checks passed")
    d = state["draft"]
    verdict, usage = await llm.structured(
        "critic", "critic", CritiqueLLM,
        revision=rnd, max_revisions=MAX_REV, min_words=WORDS[0], max_words=WORDS[1],
        summary=state["job_spec"]["summary"], questions="; ".join(state["job_spec"]["screening_questions"]) or "(none)",
        checks=checks, evidence=evidence_block(state["evidence"]),
        draft=d["cover_letter"] + "\n\nScreening answers:\n" + "\n".join(d["screening_answers"]))
    approved = verdict.approved and not hard
    crit = Critique(approved=approved, issues=hard + verdict.issues, revision_instructions=verdict.revision_instructions,
                    round=rnd)
    out = {"critiques": [crit.model_dump()], "usage": [usage]}
    if not approved and rnd < MAX_REV:
        out["revisions"] = rnd + 1          # send back to the Writer
    return out


def after_critic(state) -> str:
    """Loop back to the Writer only if not approved and revisions are left."""
    from agent.nodes.base import STOP, over_budget

    if state.get("status") in STOP:
        return "__end__"
    if over_budget(state):
        return "needs_attention"
    last = state["critiques"][-1]
    return "writer" if (not last["approved"] and last["round"] < MAX_REV) else "compliance"
