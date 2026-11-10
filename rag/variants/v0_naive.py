"""V0 - naive dense baseline (required): fixed chunks, top-k cosine on the WHOLE job post."""

from rag.pipeline import RagConfig

CONFIG = RagConfig(name="v0_naive", query="whole", retrieval="dense", rerank=False, corrective=False)
