# GigBid Portfolio MCP server

An MCP server that answers one question for an AI assistant: what can this freelancer prove? It
searches a portfolio (case studies, repositories, client reviews, past proposals, a CV) and returns
the items that support a claim, so an assistant writing a proposal or a cover letter can cite real
work instead of inventing it. It is read-only.

It is the evidence server behind GigBid (https://github.com/joe1o/gigbid), and it works on its own
with any portfolio file in the format below.

## Tools, resources and prompts

| Kind | Name | What it does |
|---|---|---|
| Tool | `search_evidence(requirement, k, filters)` | Items that prove a requirement, best first, with a support score |
| Tool | `map_requirements(requirements)` | For each requirement, the evidence found or "no evidence" (corrective retrieval, refuses weak matches) |
| Tool | `get_case_study(id)` | One portfolio item in full |
| Tool | `list_skills()` | Every skill in the portfolio and how many items show it |
| Resource | `portfolio://profile`, `portfolio://case/{id}`, `portfolio://proposal/{id}` | The same data by address, for hosts that open resources |
| Prompt | "Which of my projects fit this job?", "Answer a screening question from my portfolio", "Write a specific opening line for a job" | Ready-made prompts that call the tools |

All tools are marked read-only and idempotent. Retrieval uses `BAAI/bge-small-en-v1.5` embeddings
and an `ms-marco-MiniLM-L-6-v2` reranker, both open models that run on a CPU (about 150 MB,
downloaded on first use).

## Run it

### With Docker

```bash
docker build -t gigbid-portfolio-mcp -f mcp_servers/portfolio/Dockerfile https://github.com/joe1o/gigbid.git
docker run -i --rm -v /path/to/my_portfolio.json:/data/portfolio.json gigbid-portfolio-mcp
```

The image runs the server over stdio and reads the portfolio from `/data/portfolio.json`. Without
the `-v` mount it serves the sample web developer portfolio.

### With Python (3.11 or later)

```bash
git clone https://github.com/joe1o/gigbid && cd gigbid
pip install -e .
PORTFOLIO_PATH=/path/to/my_portfolio.json python -m mcp_servers.portfolio.server --stdio
```

To serve it over Streamable HTTP instead, drop `--stdio`. The HTTP server listens on port 8091
(`PORTFOLIO_MCP_PORT`) at `/mcp` and requires `Authorization: Bearer <MCP_AUTH_TOKEN>`.

### In Claude Desktop or another MCP host

```json
{
  "mcpServers": {
    "portfolio": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "-v", "/path/to/my_portfolio.json:/data/portfolio.json", "gigbid-portfolio-mcp"]
    }
  }
}
```

## Portfolio file format

One JSON file with a few profile fields and a list of items. The three sample portfolios in
`data/personas/*/portfolio.json` follow this format.

```json
{
  "persona_id": "me",
  "name": "Your Name",
  "headline": "Full-stack web developer: React, Next.js and Node",
  "category": "web",
  "items": [
    {
      "id": "my-case-1",
      "type": "case_study",
      "title": "Short title of the project",
      "project": "project-slug",
      "skills": ["Next.js", "Stripe"],
      "date": "2025-07",
      "client_industry": "retail",
      "outcome": null,
      "text": "What you built, for whom, with which tools, and the result you can show."
    }
  ]
}
```

`type` is one of `cv`, `case_study`, `repo_readme`, `code`, `review` or `past_proposal`. `text` is what
gets searched, so put the facts a client would care about there. The server re-reads the file when
it changes.

## Tests

`pytest mcp_servers/portfolio/tests` runs the server's own tests, and the contract snapshot in
`tests/contract/` fails if a tool's schema changes without the snapshot being updated.
