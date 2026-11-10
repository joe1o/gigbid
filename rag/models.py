"""
models.py - the two small open models RAG uses. Both run on a normal CPU.

    Embedding model (nomic-embed-text v1.5, quantised):
        turns text into a list of 768 numbers (a "vector") so that texts with similar
        MEANING get similar vectors. Comparing vectors = "semantic search".
    Reranker (ms-marco MiniLM cross-encoder):
        reads a (question, passage) pair TOGETHER and scores how well the passage answers
        it. Slower than vectors but more precise, so we only use it on the top ~20 candidates.

Models download once (from Hugging Face) into data/processed/models/.
"""

import threading
from functools import lru_cache

import numpy as np

from agent.settings import CONFIG, PROCESSED

CACHE = str(PROCESSED / "models")
EMB_MODEL = CONFIG["rag"]["embedding_model"]
RERANK_MODEL = CONFIG["rag"]["reranker_model"]

# nomic models expect a task prefix on every text (their documented usage).
_IS_NOMIC = "nomic" in EMB_MODEL
DOC_PREFIX = "search_document: " if _IS_NOMIC else ""
QUERY_PREFIX = "search_query: " if _IS_NOMIC else ""


_load_lock = threading.Lock()      # two threads must not load (or download) the same model at once


@lru_cache(maxsize=1)
def _embedder():
    from fastembed import TextEmbedding

    with _load_lock:
        return TextEmbedding(EMB_MODEL, cache_dir=CACHE)


@lru_cache(maxsize=1)
def _reranker():
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    with _load_lock:
        return TextCrossEncoder(RERANK_MODEL, cache_dir=CACHE)


def _normalise(m: np.ndarray) -> np.ndarray:
    """Scale every vector to length 1, so a dot product = cosine similarity."""
    return m / np.clip(np.linalg.norm(m, axis=-1, keepdims=True), 1e-12, None)


def embed_documents(texts: list[str]) -> np.ndarray:
    return _normalise(np.array(list(_embedder().embed([DOC_PREFIX + t for t in texts]))))


def embed_query(text: str) -> np.ndarray:
    return _normalise(np.array(list(_embedder().embed([QUERY_PREFIX + text])))[0])


def rerank_scores(query: str, passages: list[str]) -> list[float]:
    """Cross-encoder relevance score for each passage (higher = more relevant; roughly -10..10)."""
    if not passages:
        return []
    return [float(s) for s in _reranker().rerank(query, passages)]
