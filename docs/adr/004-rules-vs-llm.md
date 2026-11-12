# ADR 004: Rules where rules are enough, models where language is needed

Status: accepted

Decide, Pricing, Compliance and the Scout are rules; the Fit Matcher and claim verification use
the reranker (no LLM); the Risk Assessor combines rules with a small model's second opinion.
Only the Job Analyst, Writer, Critic and Client Liaison call an LLM.

Why. These steps have exact definitions (a price inside a budget, an email address is
contact info, a job under the user's floor is skipped). Rules are free, instant, deterministic
and explainable in the viva; an LLM adds cost, latency and variance without adding accuracy.
Policy values (costs, rules, required statements, thresholds) live in `gigsim/policy.yaml` and
`agent/config.yaml`, so they change without code changes.

Consequence. Decisions are reproducible, the CI smoke eval can run them with a fake model,
and the token budget is spent on the writing that needs it.
