"""
pipeline.py - ONE retrieval pipeline whose parts can be switched on and off.

Each RAG variant (rag/variants/*.py) is just a different combination of switches:

    query      : "whole"     -> search once with the whole job post             (V0)
                 "decompose" -> one search per requirement, then merge         (V1)
    retrieval  : "dense"     -> meaning-based search with embeddings            (V0)
                 "hybrid"    -> dense + BM25 keyword search, fused with RRF    (V2)
    rerank     : True        -> a cross-encoder re-scores the top candidates    (V3)
    corrective : True        -> grade evidence, re-query if weak, refuse if none (V8)

Because the parts are switches, the ablation study ("remove one part from the
best pipeline") is just a different set of switches - no new code.
"""

import re
import time
from dataclasses import dataclass, replace

import numpy as np

from agent.settings import CONFIG
from rag import models
from rag.index.store import get_index

CANDIDATES = CONFIG["rag"]["candidates"]


@dataclass(frozen=True)
class RagConfig:
    name: str
    query: str = "whole"          # whole | decompose
    retrieval: str = "dense"      # dense | hybrid
    rerank: bool = False
    corrective: bool = False

    def without(self, part: str) -> "RagConfig":
        """The same pipeline with one part removed (for ablations)."""
        off = {"decompose": {"query": "whole"}, "hybrid": {"retrieval": "dense"},
               "rerank": {"rerank": False, "corrective": False}, "corrective": {"corrective": False}}[part]
        return replace(self, name=f"{self.name} - {part}", **off)


# ---------------------------------------------------------------------------
# Small building blocks
# ---------------------------------------------------------------------------
def rrf(rankings: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    """
    Reciprocal Rank Fusion: merge several ranked lists into one.
    Each list gives an item 1/(k + rank) points; points are summed. Items ranked high
    in ANY list float to the top, and no score scales need to be compared.
    """
    points: dict[str, float] = {}
    for ranking in rankings:
        for rank, key in enumerate(ranking, start=1):
            points[key] = points.get(key, 0.0) + 1.0 / (k + rank)
    return sorted(points.items(), key=lambda p: p[1], reverse=True)


def requirements_for(job: dict) -> list[str]:
    """
    Split a job into separate requirements (for "decompose").
    The listed skills, plus each meaningful sentence of the description.
    In the full graph the Job Analyst (LLM) supplies better requirements instead.
    """
    reqs = list(job.get("required_skills", []))
    for sentence in re.split(r"(?<=[.!?])\s+", job.get("description", "")):
        if len(sentence.split()) >= 5:
            reqs.append(sentence.strip())
    return reqs[:8]


# ---------------------------------------------------------------------------
# Single-query search over chunks
# ---------------------------------------------------------------------------
def search_chunks(persona_id: str, query: str, cfg: RagConfig) -> list[tuple[dict, float]]:
    """Ranked (chunk, score) pairs for one query."""
    idx = get_index(persona_id)
    dense = idx.dense_scores(query)
    if cfg.retrieval == "hybrid":
        bm = idx.bm25_scores(query)
        dense_rank = [idx.chunks[i]["chunk_id"] for i in np.argsort(-dense)]
        bm_rank = [idx.chunks[i]["chunk_id"] for i in np.argsort(-bm) if bm[i] > 0]
        by_id = {c["chunk_id"]: c for c in idx.chunks}
        ranked = [(by_id[cid], s) for cid, s in rrf([dense_rank, bm_rank])]
    else:
        ranked = [(idx.chunks[i], float(dense[i])) for i in np.argsort(-dense)]

    if cfg.rerank:
        top = ranked[:CANDIDATES]
        scores = models.rerank_scores(query, [c["text"] for c, _ in top])
        ranked = sorted(zip([c for c, _ in top], scores), key=lambda p: p[1], reverse=True)
    return ranked


def to_items(ranked_chunks: list[tuple[dict, float]]) -> list[tuple[str, float]]:
    """Several chunks can come from one item: keep each item once, at its best chunk's position."""
    seen: dict[str, float] = {}
    for chunk, score in ranked_chunks:
        seen.setdefault(chunk["item_id"], score)
    return list(seen.items())


def search_items(persona_id: str, query: str, cfg: RagConfig) -> list[tuple[str, float]]:
    return to_items(search_chunks(persona_id, query, cfg))


# ---------------------------------------------------------------------------
# Whole-job retrieval (what the Fit Matcher and the evaluation use)
# ---------------------------------------------------------------------------
def retrieve_for_job(persona_id: str, job: dict, cfg: RagConfig, k: int = 10,
                     requirements: list[str] | None = None) -> dict:
    """
    Returns {
      "ranked":          [(item_id, score), ...]  merged evidence, best first (top k)
      "per_requirement": [{"requirement", "evidence": [ids], "top_score", "status"}]
      "latency_ms":      float
    }
    status = found | none ("none" = the corrective loop refused to claim this requirement)
    """
    t0 = time.perf_counter()
    if cfg.query == "whole":
        ranked = search_items(persona_id, f"{job['title']}. {job['description']}", cfg)
        return {"ranked": ranked[:k], "per_requirement": [], "latency_ms": (time.perf_counter() - t0) * 1000}

    reqs = requirements or requirements_for(job)
    per_req, rankings = [], []
    for req in reqs:
        if cfg.corrective:
            from rag.variants.v8_corrective import corrective_search

            hits, status, used = corrective_search(persona_id, req, job, cfg)
        else:
            hits, status, used = search_items(persona_id, req, cfg), "found", req
        ids = [i for i, _ in hits[:5]]
        per_req.append({"requirement": req, "query_used": used, "evidence": ids, "status": status,
                        "top_score": round(hits[0][1], 4) if hits else None})
        if status == "found":
            rankings.append(ids)
    ranked = rrf(rankings)[:k]
    return {"ranked": ranked, "per_requirement": per_req, "latency_ms": (time.perf_counter() - t0) * 1000}
