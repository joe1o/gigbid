"""
fake_llm.py - canned model answers for tests and CI (GIGBID_FAKE_LLM=1).

They are simple and deterministic so tests can check the GRAPH (routing, approvals,
persistence, budgets) without paying for or waiting on a real model. Real runs never
use this file.
"""

import re

from agent.handoffs import CritiqueLLM, IntentOut, JobExtract, RiskOpinion, WriterOut

FAKE_LETTER = (
    "Your project needs a reliable result that your team can keep using after handover, so I would start by "
    "agreeing on the exact success measure with you and checking a sample of your data in the first two days. "
    "Then I would build a simple first version, share it early so you can react, and improve it step by step "
    "with short written updates. At the end you would get clean, documented code, a short guide for your team "
    "and a call to walk through it. If that plan sounds right, I can start this week and send the first "
    "version within five working days."
)


def fake_structured(prompt: str, schema, vars: dict):
    name = schema.__name__
    if schema is JobExtract:
        skills = [s.strip() for s in vars.get("skills", "").split(",") if s.strip()]
        return JobExtract(summary=f"The client needs help with: {vars.get('title', 'a project')}.",
                          deliverables=["working solution", "documentation"], requirements=skills or ["general"])
    if schema is RiskOpinion:
        return RiskOpinion(is_scam=False, signals=[], explanation="fake model: no extra signals")
    if schema is WriterOut:
        n = len(re.findall(r"^\d+\.", vars.get("questions", ""), re.MULTILINE))
        return WriterOut(cover_letter=FAKE_LETTER,
                         screening_answers=["I would answer this in our first call with a concrete plan."] * n)
    if schema is CritiqueLLM:
        ok = int(vars.get("revision", 0)) >= 1          # first draft is sent back once, then approved
        return CritiqueLLM(approved=ok, issues=[] if ok else ["opening could be more specific"],
                           revision_instructions="" if ok else "Name the client's problem in the first sentence.")
    if schema is IntentOut:
        text = vars.get("message_block", "").lower()
        if "call" in text or "times" in text:
            return IntentOut(intent="interview_request", summary="wants a call")
        m = re.search(r"\$(\d+)", text)
        if m:
            return IntentOut(intent="negotiation", summary="asks for a lower price", offered_amount=float(m.group(1)))
        if "?" in text:
            return IntentOut(intent="question", summary="asks a question")
        return IntentOut(intent="other", summary="other")
    raise ValueError(f"no fake for {name}")


def fake_text(prompt: str, vars: dict) -> str:
    return "Thanks for your message. " + vars.get("instruction", "")[:300]
