# Hypotheses (written BEFORE running any experiment)

Committed before the first evaluation run, so the git history shows the prediction came first.

## R&D question B: retrieval

**H-B1 (main).** Requirement decomposition plus hybrid BM25+dense retrieval (V2 on top of V1)
raises evidence Recall@5 by at least 15 points over V0 (naive dense on the whole job post),
averaged over the three personas.

*Why I expect it:* the job post mixes several asks, so one embedding of the whole post blurs
them; one query per requirement keeps each ask sharp. Exact tool names ("Celery", "Prisma",
"dbt") are easy for BM25 and easy to blur for a small embedding model.

**H-B2.** The gain is largest on the **vague** job posts (short descriptions with 1-2 listed
skills), where V0 has little text to work with, and smallest on detailed posts.

**H-B3.** Cross-encoder reranking (V3) adds less than 5 points of Recall@5 on top of V2,
because the candidate pool is small (about 13 items per persona); it mainly helps MRR (the
rank of the first correct item), not recall.

**H-B4.** The corrective loop (V8) does not raise Recall@5 on good-fit jobs, but returns
**no evidence** for most requirements of poor-fit jobs, which is what the Fit Matcher needs to
recommend "skip".

**Pre-registered decision rule:** ship the simplest variant within 2 points of the best
Recall@5, with p95 latency under 2 s per job on CPU.
