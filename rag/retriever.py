"""
retriever.py - "find the portfolio items that best match this requirement".

For Phase 2 this is a simple keyword search (BM25) so the Portfolio MCP server
works. In Phase 3 this file becomes a factory that picks the RAG variant
(V0, V1, V2, ...) named in agent/config.yaml - the one our evaluation chose.
"""

import re

from rank_bm25 import BM25Okapi

from rag.corpus import items


def tokenize(text: str) -> list[str]:
    """Lower-case words, keeping things like 'scikit-learn' and 'next.js' together."""
    return re.findall(r"[a-z0-9][a-z0-9+#.\-]*", text.lower())


def item_text(item: dict) -> str:
    """The text we index for one item: title + skills + body."""
    return f"{item['title']} {' '.join(item['skills'])} {item['text']}"


def _passes(item: dict, filters: dict | None) -> bool:
    if not filters:
        return True
    if filters.get("types") and item["type"] not in filters["types"]:
        return False
    if filters.get("project") and item["project"] != filters["project"]:
        return False
    return not (filters.get("outcome") and item["outcome"] != filters["outcome"])


def search(persona_id: str, query: str, k: int = 5, filters: dict | None = None) -> list[dict]:
    """Return up to k items (with a 'score'), best first."""
    # Score against the WHOLE portfolio first (word rarity is measured over everything),
    # then apply the filters. Filtering first breaks BM25 when only 1-2 items remain.
    pool = items(persona_id)
    bm25 = BM25Okapi([tokenize(item_text(i)) for i in pool])
    scores = bm25.get_scores(tokenize(query))
    ranked = sorted(zip(pool, scores), key=lambda p: p[1], reverse=True)
    ranked = [(i, s) for i, s in ranked if s > 0 and _passes(i, filters)]
    return [{**item, "score": round(float(s), 4)} for item, s in ranked[:k]]
