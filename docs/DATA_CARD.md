# Data card

## Summary: real vs synthetic

| Dataset | Real or synthetic | Source | License |
|---|---|---|---|
| Persona portfolios (3) | Synthetic | written for this project | MIT, same as the repository |
| Job ideas and 54 job posts | Synthetic | written for this project, expanded by `gigsim/seed.py` | MIT |
| Clients (15) with histories and hidden preferences | Synthetic | written for this project | MIT |
| Market price history (450 budgets) | Synthetic | log-normal samples per category, `gigsim/seed.py` | MIT |
| Gold labels (dev set) | Synthetic | derived from the hand-written job ideas | MIT |
| Human judge labels (30 proposals) | Real human judgement | labelled by the author, `evals/datasets/judge_labels.csv` | MIT |
| Policy pack | Course material + synthetic | starter kit rules, extended for the policy update | as provided |

No real client, freelancer or platform data is used anywhere. Everything above is safe to
show publicly. All synthetic files are marked as synthetic in this card and in their folders.

## Why synthetic data, and the Kaggle datasets
The course GigSim simulator, persona corpora and dev set were not in the starter kit. The
teaching team later listed Kaggle datasets of real Upwork postings and contracts as an option.
They were considered but not used, for three reasons: the evaluation needs gold labels (should
bid, is scam, which portfolio items prove fit, fair price band), which real postings do not
have; scams and planted prompt injections had to be controlled; and the time left before the
deadline. The cost is that price statistics and job wording are less varied than real Upwork
data, and results may not transfer directly to real postings. Replacing the synthetic price
history with real budgets from the "Upwork Job Postings 2024" dataset is the first planned
improvement; only `data/gigsim/market_history.json` would change.

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
