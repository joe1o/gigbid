# ADR 001: Which RAG design ships

**Status:** accepted · **Evidence:** `evals/results/rag_eval.json`, `evals/results/rag_table.md`
· **Hypotheses (written first):** `evals/HYPOTHESES.md`

## Context
Five variants were built as switches on one pipeline (`rag/pipeline.py`): V0 naive dense,
V1 requirement decomposition, V2 hybrid BM25+dense with RRF, V3 cross-encoder rerank and V8
corrective loop (LangGraph). They were scored on the 39 dev jobs with gold evidence
(good-fit + injection jobs, all 3 personas) and 6 poor-fit jobs.

## Results (from rag_table.md)
| variant | Recall@5 | MRR | nDCG@10 | p95 ms | no-evidence (good / poor-fit) |
|---|---|---|---|---|---|
| V0 naive | **0.947** | **1.0** | 0.957 | 47 | - |
| V1 decompose | 0.796 | 0.838 | 0.823 | 85 | - |
| V2 hybrid | 0.796 | 0.836 | 0.802 | 88 | - |
| V3 rerank | 0.810 | 0.794 | 0.783 | 1249 | - |
| V8 corrective | 0.854 | 0.884 | 0.854 | 1693 | **0.02 / 1.00** |

Ablation of the full pipeline (V8): removing decomposition *raises* Recall@5 to 0.944;
removing hybrid changes nothing; removing rerank or the corrective step lowers it.

## Hypotheses vs results
- **H-B1 rejected.** Decomposition + hybrid did not add 15 points; it *lost* 15 (0.947 to 0.796).
  Rule-based decomposition turns generic skills ("Python", "React", "SQL") into separate
  queries that pull in the CV and loosely related items, pushing the specific evidence down.
  With ~13 items per persona, one embedding of the whole post is already enough.
- **H-B2 rejected.** V0 was not weaker on vague posts (0.967 vague vs 0.933 detailed).
- **H-B3 partly held.** Rerank added under 2 points of recall over V2, and it did not help MRR either.
- **H-B4 held.** V8 refuses evidence for 100% of poor-fit requirements and only 2% of good-fit ones.

## Decision
Following the pre-registered rule (simplest variant within 2 points of the best Recall@5, p95
under 2 s), **V0 ships for evidence retrieval** (`rag.variant: v0_naive`): best recall, perfect
MRR, 47 ms. **V8 is used only for the requirement-to-evidence matrix** in the Fit Matcher
(`rag.fit_variant: v8_corrective`), because its "no evidence" signal separates poor-fit from
good-fit jobs (100% vs 2%), which V0 cannot express. The vector store is a NumPy matrix per
persona (about 40 chunks), because a vector database adds a service without benefit at this size.

## Limits
Small synthetic corpus (13 items per persona, about 2.5 gold items per job), so recall saturates
easily. The decomposition here is rule-based. Phase 4's LLM Job Analyst produces cleaner
requirements, which is re-measured there. The corrective threshold (-7.0) was chosen from the
dev-set score distribution, so it may be slightly optimistic.
