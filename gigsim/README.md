# GigSim (our simulator)

The course's GigSim simulator and persona data were not included in the starter kit we
received, so this folder is **our own small stand-in** with the same job: a safe,
repeatable fake marketplace for development and evaluation. Once built, it is treated as
frozen (CI checks that agents never touch it directly; they go through the Marketplace MCP server).

```bash
python -m gigsim.seed                       # regenerate jobs + gold labels (deterministic)
uvicorn gigsim.app:app --port 8081          # run it; API docs at http://localhost:8081/docs
```

| Endpoint | What it does |
|---|---|
| `GET /health` | is it up? |
| `GET /policy` | platform rules + Connects pricing (from `policy.yaml`) |
| `GET /jobs?q=&category=&posted_after=` | search visible jobs (new jobs appear over time) |
| `GET /jobs/{id}` | one job |
| `GET /clients/{id}` | client history (spend, hires, rating, account age) |
| `GET /market/stats?category=` | historical price quartiles |
| `GET /me/connects` | Connects balance |
| `POST /proposals[?dry_run=true]` | submit (needs `Idempotency-Key`) or preview cost |
| `GET /proposals`, `GET /proposals/{id}` | status: submitted, viewed, replied, interview, hired, lost |
| `GET /threads`, `GET/POST /threads/{id}/messages` | client conversations |
| `POST /admin/reset` | wipe state (tests/evals) |

**Platform behaviour:** bearer-token auth, 60 calls/min rate limit (HTTP 429), 2% random
HTTP 503s, idempotent writes, and simulated clients with hidden preferences
(`client_sim.py`) that decide to reply, interview or hire.
