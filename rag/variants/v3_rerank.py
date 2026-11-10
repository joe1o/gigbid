"""
V3 - cross-encoder reranking (retrieval group, required), on top of V2.
The top candidates are re-scored by a model that reads query and passage together.
"""

from rag.pipeline import RagConfig

CONFIG = RagConfig(name="v3_rerank", query="decompose", retrieval="hybrid", rerank=True, corrective=False)
