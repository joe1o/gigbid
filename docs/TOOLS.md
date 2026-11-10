# MCP tool inventory

Agents never call GigSim, Upwork, a database or a file directly; every capability is an MCP
tool. All three servers use the official MCP Python SDK (FastMCP), run over Streamable HTTP,
and require `Authorization: Bearer $MCP_AUTH_TOKEN`. The caller is identified by the
`X-GigBid-User` header, and `X-Trace-Id` carries one trace id from the UI to the audit log.

Annotation shorthand: **RO** readOnlyHint · **D** destructiveHint · **I** idempotentHint · **OW** openWorldHint.
Signatures are frozen by `tests/contract/snapshots/tools.json` (CI fails on accidental changes).

## Our servers

| Tool | Server | Read / write | Annotations | Auth | Used by (allowlist) |
|---|---|---|---|---|---|
| `search_jobs` | marketplace | read | RO, I, OW | bearer + user | scout |
| `get_job` | marketplace | read | RO, I, OW | bearer + user | scout |
| `get_client_history` | marketplace | read | RO, I, OW | bearer + user | risk_assessor |
| `get_connects_balance` | marketplace | read | RO, I, OW | bearer + user | pricing |
| `get_policy` | marketplace | read | RO, I, OW | bearer + user | risk_assessor, pricing |
| `market_stats` | marketplace | read | RO, I, OW | bearer + user | pricing |
| `list_proposals` | marketplace | read | RO, I, OW | bearer + user | pipeline |
| `list_threads` | marketplace | read | RO, I, OW | bearer + user | client_liaison, pipeline |
| `list_messages` | marketplace | read | RO, I, OW | bearer + user | client_liaison |
| `create_proposal_draft` | marketplace | write (local draft, dry-run preview) | not RO, not D, I | bearer + user + idempotency key | submitter (after approval) |
| `submit_proposal` | marketplace | write (spends Connects) | not RO, **D**, I, OW, `dry_run` | bearer + user + idempotency key | submitter (after approval) |
| `send_message` | marketplace | write | not RO, **D**, I, OW, `dry_run` | bearer + user + idempotency key | client_liaison (after approval) |
| `search_evidence` | portfolio | read | RO, I | bearer + user | fit_matcher, writer, critic |
| `get_case_study` | portfolio | read | RO, I | bearer + user | writer, critic |
| `list_skills` | portfolio | read | RO, I | bearer + user | fit_matcher |
| `get_free_slots` | workspace | read | RO, I | bearer + user | client_liaison |
| `create_interview_hold` | workspace | write (tentative only) | not RO, not D, I | bearer + user + idempotency key | client_liaison (after approval) |
| `create_email_draft` | workspace | write (draft only, never sent) | not RO, not D, I | bearer + user + idempotency key | client_liaison (after approval) |

Portfolio also exposes **resources** `portfolio://profile`, `portfolio://case/{id}`,
`portfolio://proposal/{id}` and **prompts** "Answer a screening question from my portfolio",
"Write a specific opening line for a job", "Which of my projects fit this job?".

Marketplace server extras: per-user rate limit (40/min, under GigSim's 60/min), append-only
audit log `data/processed/audit/marketplace.jsonl` (user, tool, arguments, result, trace id,
with emails, phones and card numbers masked), and errors mapped to `MARKETPLACE_UNAVAILABLE`
so the client can switch to degraded mode.

The workspace server is a **local mock** (fixed busy blocks plus holds in SQLite), which the
assignment allows; agents only ever see its MCP tools.

## Third-party servers

| Server | Used for | Trust rationale (one line) |
|---|---|---|
| Upwork official MCP (`https://mcp.upwork.com/mcp`) | live mode via `UpworkLiveAdapter` (stub, not verified) | Upwork's own server with OAuth 2.1 and draft-only writes is the only sanctioned automation path: no scraping or cookies. |
| GitHub official MCP (`github/github-mcp-server`) | reading the freelancer's own repo READMEs and code for ingestion | GitHub's first-party server, read-only scope on a fine-grained token, used only on the user's own repositories. |
