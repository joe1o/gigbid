# Data card

All data is **synthetic** (written by me for this project) and safe to show publicly.
No real client data is used anywhere.

## Why our own data
The course GigSim simulator, persona corpora and dev set were not in the starter kit I
received. I built smaller stand-ins with the same structure. This limits how far the
numbers generalise, and the report says so.

## Persona portfolios: `data/personas/<persona>/portfolio.json`
| Persona | Items | Item types |
|---|---|---|
| `ml_engineer` (Sara Malik) | 13 | cv, case_study, repo_readme, code, review, past_proposal |
| `web_developer` (Omar Raza) | 13 | same |
| `data_analyst` (Hina Javed) | 12 | same |

Metadata on every item: `id, type, title, project, skills, date, client_industry, outcome`
(`outcome` = won / replied / ignored for past proposals).

Deliberately "messy", to defeat naive retrieval:
- the same project described twice in different words (`ml-cs-legal-rag` vs `ml-cs-contract-qa`);
- skills that appear **only in code**, not in the README (Celery in `ml-code-sentiment`,
  Prisma in `web-code-shop`, Redis in `web-code-chat`);
- past proposals whose **outcome** matters more than their wording (a generic one was ignored).

## Jobs: `data/gigsim/jobs.json` (54 jobs, made by `gigsim/seed.py`, seed 42)
Per category (ml / web / data): 10 good-fit jobs (each idea once detailed, once vague),
2 poor-fit, 1 absurdly low budget, 2 scams, 2 legit jobs with planted prompt-injection
text, 1 duplicate repost.

## Gold labels: `evals/datasets/dev_labels.json`
Per job: `should_bid`, `is_scam`, `has_injection`, `duplicate_of`, `gold_evidence`
(portfolio ids that prove fit) and `fair_band` (fair price range). Labels come from the
hand-written job ideas, so they are known by construction. 36 bid / 18 skip.

## Clients: `data/gigsim/clients.json`
15 clients: 12 normal, 1 difficult, 2 scam accounts. Public history is served by the API;
hidden preferences (dislikes generic openings, budget tolerance, responsiveness, sends
injection text in messages) are used only by the simulated client.

## Market history: `data/gigsim/market_history.json`
150 synthetic historical budgets per category (log-normal around a category median), for
price statistics.
