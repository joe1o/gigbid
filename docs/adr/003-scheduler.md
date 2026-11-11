# ADR 003: In-process scheduler instead of a Celery/Redis worker

**Status:** accepted

**Context.** E1 asks that scouting and long runs execute outside web requests, on a schedule,
idempotently. The suggested stack is Celery, Arq or Dramatiq on Redis.

**Decision.** Run the scout scheduler, graph runs and the recovery loop as asyncio background
tasks in the API process (`apps/api/services.py`), with a semaphore limiting concurrent runs.

**Why.** At this scale (a few users, tens of jobs per scout) the guarantees the worker exists
for are already provided by other parts: durability by the Postgres checkpointer (a crashed run
resumes from its last step), idempotency by the Scout's seen-job store and idempotency keys on
every write, and "not inside a request" by background tasks. A Redis service and a worker
process would double the deployment's moving parts on a free host for no new guarantee.

**Cost.** Runs share the API process's CPU; the RAG models run in worker threads so requests
stay responsive. If the load grew, `run_bid` / `scout_now` can move behind an Arq queue
unchanged, because they already take only `(runtime, user, job)`.
