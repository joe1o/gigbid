# Docker

One image (`/Dockerfile`) contains every GigBid service; each container runs a different
command. That keeps the build in one place, while every service still runs as its own process.

| Service | Command |
|---|---|
| gigsim | `python -m uvicorn gigsim.app:app --port 8081` |
| portfolio MCP | `python -m mcp_servers.portfolio.server` (8091) |
| marketplace MCP | `python -m mcp_servers.marketplace.server` (8092) |
| workspace MCP | `python -m mcp_servers.workspace.server` (8093) |
| api + web | `python -m uvicorn apps.api.main:app --port 8000` |
| all in one (deploy) | `python scripts/run_all.py` (supervises the five above) |

`infra/docker-compose.yml` wires them together with Postgres and an optional Ollama service.
The hosted deployment (Hugging Face Spaces) runs the all-in-one command with Neon Postgres.
