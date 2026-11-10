"""
V1 - requirement decomposition (query group, required).
One dense search per requirement, results merged with RRF. Helps posts that ask for several things.
"""

from rag.pipeline import RagConfig

CONFIG = RagConfig(name="v1_decompose", query="decompose", retrieval="dense", rerank=False, corrective=False)
