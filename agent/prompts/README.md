# Prompts

One versioned Markdown file per LLM node; no prompt text lives in Python code
(CI checks this). The first line `<!-- version: N -->` is the prompt version, recorded
with every run. Variables use `$name` and are filled by `agent/llm.py`.

| File | Node | Model (open profile) |
|---|---|---|
| `job_analyst.md` | Job Analyst | gpt-oss-20b |
| `risk_assessor.md` | Risk Assessor (second opinion) | gpt-oss-20b |
| `writer.md` | Proposal Writer | gpt-oss-120b |
| `critic.md` | Critic | gpt-oss-120b |
| `liaison_intent.md` | Client Liaison, intent | gpt-oss-20b |
| `liaison_reply.md` | Client Liaison, reply | gpt-oss-120b |

Job posts and client messages are always wrapped by `agent/safety.wrap_untrusted()`
(`$job_block`, `$message_block`, `$conversation_block`) and treated as data.
