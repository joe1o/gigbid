"""
store.py - the search index for one freelancer: a tiny in-process VECTOR STORE plus BM25.

In simple words:
    For every chunk we keep
      - its embedding vector (for meaning-based search), and
      - its words (for keyword search with BM25).
    Vectors are cached on disk by a fingerprint (hash) of the chunk text, so when
    the freelancer adds or edits work only the NEW/CHANGED chunks are embedded again.
    That is "incremental re-indexing".

Why not a vector database (Chroma, pgvector)? Each portfolio is ~40 chunks; a
NumPy matrix searches that in microseconds, needs no extra service and is easy to
explain. A database only pays off at thousands of items. (See docs/adr.)
"""

import json
import re

import numpy as np
from rank_bm25 import BM25Okapi

from agent.settings import PROCESSED
from rag import models
from rag.ingest.chunker import chunk_portfolio

INDEX_DIR = PROCESSED / "index"


def tokenize(text: str) -> list[str]:
    """Lower-case words, keeping things like 'scikit-learn' and 'next.js' together."""
    return [t.strip(".-") for t in re.findall(r"[a-z0-9][a-z0-9+#.\-]*", text.lower())]


class PersonaIndex:
    def __init__(self, persona_id: str):
        self.persona_id = persona_id
        self.chunks = chunk_portfolio(persona_id)
        self.vectors, self.newly_embedded = self._load_vectors()
        self.bm25 = BM25Okapi([tokenize(c["text"]) for c in self.chunks])

    def _load_vectors(self) -> tuple[np.ndarray, int]:
        """Reuse cached vectors; embed only chunks we have never seen."""
        INDEX_DIR.mkdir(parents=True, exist_ok=True)
        cache_file = INDEX_DIR / f"{self.persona_id}.{models.EMB_MODEL.replace('/', '_')}.json"
        cache = json.loads(cache_file.read_text()) if cache_file.exists() else {}
        missing = [c for c in self.chunks if c["hash"] not in cache]
        if missing:
            for c, v in zip(missing, models.embed_documents([c["text"] for c in missing])):
                cache[c["hash"]] = v.tolist()
            # keep only vectors for chunks that still exist (deleted work disappears too)
            cache = {c["hash"]: cache[c["hash"]] for c in self.chunks}
            cache_file.write_text(json.dumps(cache))
        return np.array([cache[c["hash"]] for c in self.chunks]), len(missing)

    def dense_scores(self, query: str) -> np.ndarray:
        """Cosine similarity of the query to every chunk."""
        return self.vectors @ models.embed_query(query)

    def bm25_scores(self, query: str) -> np.ndarray:
        return np.array(self.bm25.get_scores(tokenize(query)))


_cache: dict[tuple, PersonaIndex] = {}


def get_index(persona_id: str) -> PersonaIndex:
    """One index per persona, rebuilt automatically when the portfolio changes."""
    from rag.corpus import load_portfolio

    signature = (persona_id, json.dumps(load_portfolio(persona_id)["items"], sort_keys=True).__hash__())
    if signature not in _cache:
        _cache.clear() if len(_cache) > 8 else None
        _cache[signature] = PersonaIndex(persona_id)
    return _cache[signature]
