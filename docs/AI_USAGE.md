# AI usage disclosure

**Tool:** Claude Code (Anthropic, Claude Opus 5.5) in the Claude desktop app, used as a pair
programmer throughout. I chose the scope and design trade-offs (simulator instead of the
missing GigSim, Groq open models, Neon, Hikmah's design system, the X2 extension, cutting
Redis/Celery and live Upwork), reviewed every phase, ran the app, and asked for explanations of
each part so I can explain and change it. I am responsible for all of the code.

| Area | Files | How AI was used |
|---|---|---|
| Simulator + data | `gigsim/`, `data/` | drafted the simulator, personas and job ideas from my brief |
| MCP servers | `mcp_servers/`, `agent/mcp_client.py`, `agent/marketplace_port.py` | generated servers, schemas and tests |
| RAG + verification | `rag/`, `evals/runners/rag_eval.py` | implemented variants and the eval; I wrote the hypotheses first |
| Agents | `agent/` | implemented graphs, nodes, prompts and memory rules |
| Web app | `apps/api`, `apps/web` | generated API, UI (in my FYP's design system) and Playwright tests |
| Evals, docs | `evals/`, `docs/`, `README.md` | wrote runners and first drafts of the docs; numbers come from `evals/results/` |

## Things it got wrong that were caught

- **Caught by me:** after the first pushes I noticed the GitHub checks were red. The starter
  kit's CI failed on lint (unsorted imports) and on pytest not finding the `agent` package; the
  assistant had pushed without running the CI commands locally. Fixed, and every push since is
  checked locally first.
- **Caught by me:** a helper printed the full Neon connection string (with password) into the
  tool output while trying to mask it; I reset the database password and the assistant now only
  prints variable names from `.env`.
- **Caught by tests / runs (assistant's own bugs):** claim verification skipped any sentence
  containing "I can" (so "my ten years of Kubernetes ensures I can..." was never checked); BM25
  scored a filtered pool of one item as zero; the onboarding route guard reused stale React state
  and looped back to step 1; the inbox stopped polling after "Find new jobs"; scouting 17 jobs
  tripped our own rate limiter and dead-lettered jobs instead of waiting; CPU-bound reranking
  blocked the server's event loop on CI. Each has a regression test or a CI job now.
