# GigBid API (FastAPI)

`main.py` app + lifespan (durable runtime, reviewer login, recovery loop) · `routers/` auth, jobs,
approvals, runs (SSE), proposals (pipeline), messages, analytics · `streaming.py` LangGraph updates to
Server-Sent Events · `services.py` background runs, scout, degraded mode · `auth/` passwords, sessions,
encrypted tokens · `schemas/` typed request/response models (source of the web app's TypeScript types).

```bash
uvicorn apps.api.main:app --reload --port 8000     # docs at /docs
python -m apps.api.export_openapi                  # write apps/web/openapi.json
```
