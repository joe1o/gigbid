"""
V2 - hybrid BM25 + dense with reciprocal rank fusion (retrieval group, required), on top of V1.
BM25 catches exact tool names ("Celery", "Prisma", "dbt") that embeddings can blur.
"""

from rag.pipeline import RagConfig

CONFIG = RagConfig(name="v2_hybrid", query="decompose", retrieval="hybrid", rerank=False, corrective=False)
