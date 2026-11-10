"""
Claim verification node (B3) - runs between the Writer and the Critic.

Every claim in the cover letter and screening answers is checked against the
evidence the Writer was given (rag/verify.py). Unsupported claims are REMOVED before
the Critic sees the draft. The rate BEFORE removal is kept for the report.
"""

from agent.handoffs import ClaimReport
from agent.nodes.base import node
from rag.verify import verify_claims


@node("verify_claims")
async def verify_claims_node(state, config):
    raw, evidence = state["draft_raw"], state["evidence"]
    letter = verify_claims(raw["cover_letter"], evidence)
    answers = [verify_claims(a, evidence) for a in raw["screening_answers"]]
    claims = letter["claims"] + [c for a in answers for c in a["claims"]]
    removed = letter["removed"] + [r for a in answers for r in a["removed"]]
    rate = sum(c["label"] == "unsupported" for c in claims) / len(claims) if claims else 0.0
    draft = {**raw, "cover_letter": letter["cleaned_draft"],
             "screening_answers": [a["cleaned_draft"] for a in answers]}
    report = ClaimReport(claims=claims, unsupported_rate_before=round(rate, 3), removed=removed)
    return {"draft": draft, "claims": report.model_dump()}
