# ADR 002: Hosting on Hugging Face Spaces (Docker) with Neon Postgres

**Status:** accepted

**Context.** The deployed link must run the open profile, stay live until grades are released,
and survive the instructor's hidden test run. GigBid runs five processes, and two of them load
open CPU models (embeddings 130 MB, reranker 80 MB, plus ONNX runtime).

**Measured need:** about 700 MB RAM. Render's free web service has 512 MB, which would crash.
Hugging Face Spaces' free CPU tier gives 2 vCPU and 16 GB RAM for a Docker Space.

**Decision.** One Docker image, `scripts/run_all.py` as the entrypoint (supervises and restarts
the processes), Neon Postgres outside the container for checkpoints and memory, Groq for the
open models.

**Trade-offs.** A free Space sleeps after long inactivity and needs about a minute to wake;
data inside the container (GigSim's own state) resets on restart, while everything GigBid must
keep lives in Postgres. Render works with the same image on a paid instance.
