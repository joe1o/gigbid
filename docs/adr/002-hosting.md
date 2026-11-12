# ADR 002: Hosting on Render (free, Docker) with Neon Postgres

**Status:** accepted (replaces the first plan, Hugging Face Spaces)

**Context.** The deployed link must run the open profile, stay live until grades are released,
and survive the instructor's hidden test run. Locally GigBid runs five processes, and two open
CPU models (embeddings and reranker) are loaded in memory.

**Options.** Hugging Face Docker Spaces gave the most memory (16 GB) but now need a paid plan.
Render's free web service is free but has 512 MB of RAM.

**Measured need.** Five processes with `nomic-embed-text-v1.5`: about 700 MB. One process with
nomic: 568 MB peak. One process with `bge-small-en-v1.5`: 523 MB. One process with bge-small,
one model thread, batch size 8 and one graph run at a time: 441 MB, which fits.

**Decision.** Render free web service from `render.yaml`, in the Singapore region (same region as the Neon database; the first deployment in Oregon made every database call cross the Pacific, 0.7 to 1.8 s per page). One process (`scripts/serve_api.py`)
with GigSim and the MCP servers in-process, the bge-small embedding model, Neon Postgres for
checkpoints and memory, Groq for the open LLMs.

**Trade-offs.**
- Retrieval quality: bge-small has Recall@5 0.898 against 0.947 for nomic on the same 39 jobs
  (`rag_eval.json` vs `rag_eval_nomic.json`). It still passes the CI gate of 0.85.
- One graph run at a time, so several jobs are processed one after another, not in parallel.
- The MCP servers are not separate network services on the host; they still run the same MCP
  protocol in memory with the same tool allowlists. The separate-process setup is kept for local
  runs and the degraded-mode demo.
- The service sleeps after 15 minutes idle and takes about a minute to wake. GigSim's own state
  inside the container resets on a restart; everything GigBid must keep is in Postgres.
