"""
retriever.py - the factory: "give me the retrieval design named in config".

agent/config.yaml -> rag.variant decides which variant ships (chosen by our
evaluation, evals/results/rag_eval.json - not by default). Everything else in
GigBid (Portfolio MCP server, Fit Matcher, Writer) calls only these functions.
"""

import importlib

from agent.settings import CONFIG
from rag.corpus import get_item
from rag.pipeline import RagConfig, search_items
from rag.pipeline import retrieve_for_job as _retrieve_for_job

VARIANTS = ["v0_naive", "v1_decompose", "v2_hybrid", "v3_rerank", "v8_corrective"]


def get_config(name: str | None = None) -> RagConfig:
    """Load rag/variants/<name>.py and return its CONFIG."""
    name = name or CONFIG["rag"]["variant"]
    return importlib.import_module(f"rag.variants.{name}").CONFIG


def _passes(item: dict, filters: dict | None) -> bool:
    if not filters:
        return True
    if filters.get("types") and item["type"] not in filters["types"]:
        return False
    if filters.get("project") and item["project"] != filters["project"]:
        return False
    return not (filters.get("outcome") and item["outcome"] != filters["outcome"])


def search(persona_id: str, query: str, k: int = 5, filters: dict | None = None,
           variant: str | None = None) -> list[dict]:
    """One query -> up to k portfolio items (full item + 'score'), best first."""
    cfg = get_config(variant)
    out = []
    for item_id, score in search_items(persona_id, query, cfg):
        item = get_item(persona_id, item_id)
        if item and _passes(item, filters):
            out.append({**item, "score": round(float(score), 4)})
        if len(out) == k:
            break
    return out


def retrieve_for_job(persona_id: str, job: dict, k: int = 10, requirements: list[str] | None = None,
                     variant: str | None = None) -> dict:
    """Evidence for a whole job (see rag/pipeline.py for the result format)."""
    return _retrieve_for_job(persona_id, job, get_config(variant), k, requirements)
