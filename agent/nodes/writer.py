"""
Proposal Writer - drafts the cover letter and screening answers from EVIDENCE.

Model: strongest affordable (gpt-oss-120b).
Inputs: the structured JobSpec (not the raw post), evidence from the Portfolio MCP
server (shipped RAG design V0 + the Fit Matcher's matched items), the price, style
rules and outcome hints from long-term memory, and the Critic's notes on a revision.
Tools: portfolio search_evidence, get_case_study.
"""

import json

from langgraph.config import get_store

from agent import llm
from agent.handoffs import ProposalDraft, WriterOut
from agent.memory import store as memory
from agent.nodes.base import node, tools, user_settings
from agent.safety import wrap_untrusted
from agent.settings import CONFIG


def evidence_block(items: list[dict]) -> str:
    return "\n\n".join(f"[{e['id']}] ({e['type']}, {e['date']}) {e['title']}\n{e['text']}" for e in items)


@node("writer")
async def writer(state, config):
    spec, fit, job = state["job_spec"], state["fit"], state["job"]
    t = tools(state, config)
    s = user_settings(config)

    # 1. Evidence: shipped retriever on the job's summary + requirements ...
    query = (spec["summary"] + " " + ", ".join(spec["requirements"]))[:500]
    evidence = await t.call("writer", "search_evidence", {"requirement": query, "k": 6})
    have = {e["id"] for e in evidence}
    # ... plus the best item for each requirement the Fit Matcher could prove (max 3 extra).
    for row in fit["matrix"]:
        if row["status"] == "found" and row["evidence_ids"] and row["evidence_ids"][0] not in have and len(have) < 9:
            evidence.append(await t.call("writer", "get_case_study", {"id": row["evidence_ids"][0]}))
            have.add(row["evidence_ids"][0])

    # 2. Long-term memory (promoted rules only).
    store = get_store()
    style = await memory.style_rules(store, state["user_id"]) if store else []
    outcomes = await memory.outcome_hints(store, state["user_id"], job["category"]) if store else ""

    # 3. Critic's notes if this is a revision.
    notes = ""
    if state.get("critiques"):
        last = state["critiques"][-1]
        notes = ("REVISION REQUEST from the Critic - fix these:\n- " + "\n- ".join(last["issues"])
                 + f"\nInstructions: {last['revision_instructions']}\n\nPrevious draft:\n{state['draft']['cover_letter']}")

    words = CONFIG["thresholds"]["proposal_words"]
    spec_view = {k: spec[k] for k in ("title", "summary", "deliverables", "requirements", "hidden_needs", "timeline_days")}
    out, usage = await llm.structured(
        "writer", "writer", WriterOut,
        name=s.get("name", "the freelancer"), headline=s.get("headline", ""),
        min_words=words[0], max_words=words[1],
        spec=wrap_untrusted("job_spec", json.dumps(spec_view, indent=1)),
        price=f"${state['price']['amount']:.0f}",
        questions="\n".join(f"{i + 1}. {q}" for i, q in enumerate(spec["screening_questions"])) or "(none)",
        evidence=evidence_block(evidence),
        style="\n".join(f"- {r}" for r in style) or "(none learned yet)",
        outcomes=outcomes or "(none yet)", revision_notes=notes)
    draft = ProposalDraft(**out.model_dump(), job_id=job["job_id"], version=state.get("revisions", 0) + 1,
                          evidence_ids=sorted(have))
    return {"evidence": evidence, "draft_raw": draft.model_dump(), "usage": [usage]}
