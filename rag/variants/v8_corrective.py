"""
V8 - corrective RAG loop in LangGraph (agentic group, required: one of V8/V9), on top of V3.

In simple words, for each requirement:
    1. retrieve evidence
    2. GRADE it: is the best match's reranker score above the threshold?
    3. if weak  -> rewrite the query (add the job's context) and retrieve once more
    4. if still weak -> REFUSE: report "no evidence", so nobody claims this skill

This matters for jobs the freelancer should skip: their requirements end up with
"no evidence", which the Fit Matcher turns into a low fit score.

Technically it is a tiny LangGraph StateGraph: retrieve -> grade -> (rewrite -> retrieve | end).
The grader is the cross-encoder score (no LLM call), so it is free and deterministic.
"""

from functools import lru_cache
from typing import TypedDict

from langgraph.graph import END, StateGraph

from agent.settings import CONFIG as SETTINGS
from rag.pipeline import RagConfig, search_items

CONFIG = RagConfig(name="v8_corrective", query="decompose", retrieval="hybrid", rerank=True, corrective=True)
THRESHOLD = SETTINGS["rag"]["corrective_threshold"]
MAX_REWRITES = 1


class CState(TypedDict):
    persona_id: str
    requirement: str
    job_title: str
    query: str
    hits: list
    rewrites: int
    status: str
    cfg: RagConfig


def retrieve(s: CState) -> dict:
    return {"hits": search_items(s["persona_id"], s["query"], s["cfg"])}


def grade(s: CState) -> dict:
    strong = bool(s["hits"]) and s["hits"][0][1] >= THRESHOLD
    if strong:
        return {"status": "found"}
    return {"status": "weak" if s["rewrites"] < MAX_REWRITES else "none"}


def rewrite(s: CState) -> dict:
    """Give the requirement more context: the job title it came from."""
    return {"query": f"{s['requirement']} (for: {s['job_title']})", "rewrites": s["rewrites"] + 1}


def route(s: CState) -> str:
    return "rewrite" if s["status"] == "weak" else END


@lru_cache(maxsize=1)
def graph():
    g = StateGraph(CState)
    g.add_node("retrieve", retrieve)
    g.add_node("grade", grade)
    g.add_node("rewrite", rewrite)
    g.set_entry_point("retrieve")
    g.add_edge("retrieve", "grade")
    g.add_conditional_edges("grade", route, {"rewrite": "rewrite", END: END})
    g.add_edge("rewrite", "retrieve")
    # checkpointer=False: a stateless helper graph; never inherit a parent graph's saver.
    return g.compile(checkpointer=False)


def corrective_search(persona_id: str, requirement: str, job: dict, cfg: RagConfig):
    """Returns (hits, status, query_used). status is 'found' or 'none'."""
    out = graph().invoke({"persona_id": persona_id, "requirement": requirement, "job_title": job["title"],
                          "query": requirement, "hits": [], "rewrites": 0, "status": "", "cfg": cfg})
    return (out["hits"] if out["status"] == "found" else []), out["status"], out["query"]
