"""
Compliance Guard - enforces the platform policy pack. No LLM: rules are exact.

On the Writer's draft it REMOVES sentences with:
    contact details (email, phone, WhatsApp/Telegram/Skype), guarantees ("100% satisfaction"),
    off-platform payment or contact.
It BLOCKS (with a reason shown in the UI) when:
    the job itself asks for free work or off-platform contact, or too little text is left.

On the USER's edits it does not silently change their words: it re-checks them
(same rules + claim verification) and, if something is wrong, sends the draft back to
the approval screen with the reasons.
"""

import asyncio
import re

from agent.handoffs import ComplianceVerdict
from agent.nodes.base import node
from agent.safety import CONTACT, GUARANTEE, OFF_PLATFORM, sentences
from rag.verify import verify_claims

RULES = [(CONTACT, "contact details"), (GUARANTEE, "a guarantee"), (OFF_PLATFORM, "off-platform contact/payment")]


def scan(text: str) -> tuple[str, list[str]]:
    """Returns (text without violating sentences, list of violations found)."""
    paragraphs, found = [], []
    for para in re.split(r"\n\s*\n", text.strip()):      # keep paragraph breaks
        kept = []
        for s in sentences(para):
            hits = [name for rx, name in RULES if rx.search(s)]
            if hits:
                found.append(f"removed sentence with {', '.join(hits)}: \"{s.strip()[:80]}\"")
            else:
                kept.append(s.strip())
        if kept:
            paragraphs.append(" ".join(kept))
    return "\n\n".join(paragraphs), found


@node("compliance")
async def compliance(state, config):
    d = state["draft"]
    letter, fixes = scan(d["cover_letter"])
    answers = []
    for a in d["screening_answers"]:
        clean, f = scan(a)
        answers.append(clean)
        fixes += f
    blocked = None
    bad_flags = {"free_work_request", "off_platform"} & set(state["risk"]["flags"])
    if bad_flags:
        blocked = f"job violates platform policy ({', '.join(sorted(bad_flags))})"
    elif len(letter.split()) < 40:
        blocked = "too little text left after removing policy violations"
    # Statements the platform policy REQUIRES in every proposal (policy.yaml -> required_statements).
    for statement in (state.get("policy") or {}).get("required_statements", []):
        if statement.lower() not in letter.lower():
            letter = letter.rstrip() + "\n\n" + statement
            fixes.append(f'added the statement the platform requires: "{statement}"')
    verdict = ComplianceVerdict(passed=blocked is None, violations=[], fixes=fixes, blocked_reason=blocked)
    out = {"draft": {**d, "cover_letter": letter, "screening_answers": answers}, "compliance": verdict.model_dump()}
    if blocked:
        out["status"] = "blocked"
    return out


@node("compliance_edit")
async def compliance_edit(state, config):
    """Re-check the user's edited draft. Violations are reported, not silently fixed."""
    d = state["draft"]
    full = d["cover_letter"] + " " + " ".join(d["screening_answers"])
    _, found = scan(full)
    violations = [f.replace("removed sentence with", "contains") for f in found]
    checked = await asyncio.to_thread(verify_claims, full, state["evidence"])      # CPU work off the event loop
    unsupported = [c["text"] for c in checked["claims"] if c["label"] == "unsupported"]
    violations += [f'claim not supported by your portfolio: "{u[:80]}"' for u in unsupported]
    verdict = ComplianceVerdict(passed=not violations, violations=violations)
    return {"compliance": verdict.model_dump()}
