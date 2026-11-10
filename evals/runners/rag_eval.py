"""
rag_eval.py - scores every RAG variant against the answer key, then runs the ablation.

In simple words:
    For each dev job that has known "gold" evidence (the portfolio items that truly
    prove fit), every variant retrieves evidence, and we measure:
      Recall@5  - of the gold items, how many are in the top 5?            (did we find them?)
      MRR       - 1 / position of the first gold item                      (how high is the first hit?)
      nDCG@10   - rewards gold items near the top of the top 10            (is the ORDER good?)
      latency   - p50 and p95 time per job                                  (is it fast enough?)
    For corrective variants we also measure the "no evidence" rate on good-fit vs
    poor-fit jobs (poor-fit should be high, good-fit low).

    Then the ABLATION: take the best pipeline and remove one part at a time, to see
    which parts actually earn their place.

Run:  python -m evals.runners.rag_eval
Writes evals/results/rag_eval.json, rag_eval.csv and rag_table.md (every number in
the report and README comes from these files).
"""

import csv
import json
import math
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from rag.pipeline import retrieve_for_job
from rag.retriever import VARIANTS, get_config

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "evals" / "results"


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
def recall_at(ranked: list[str], gold: set[str], k: int) -> float:
    return len(set(ranked[:k]) & gold) / len(gold)


def mrr(ranked: list[str], gold: set[str]) -> float:
    return next((1 / r for r, i in enumerate(ranked[:10], start=1) if i in gold), 0.0)


def ndcg_at(ranked: list[str], gold: set[str], k: int = 10) -> float:
    dcg = sum(1 / math.log2(r + 1) for r, i in enumerate(ranked[:k], start=1) if i in gold)
    ideal = sum(1 / math.log2(r + 1) for r in range(1, min(len(gold), k) + 1))
    return dcg / ideal


def summarise(rows: list[dict]) -> dict:
    return {"n": len(rows),
            "recall@5": round(float(np.mean([r["recall@5"] for r in rows])), 3),
            "mrr": round(float(np.mean([r["mrr"] for r in rows])), 3),
            "ndcg@10": round(float(np.mean([r["ndcg@10"] for r in rows])), 3)}


# ---------------------------------------------------------------------------
# Running one variant
# ---------------------------------------------------------------------------
def evaluate(cfg, jobs: dict, labels: list[dict]) -> dict:
    rows, latencies, none_rate = [], [], defaultdict(list)
    for lab in labels:
        job = jobs[lab["job_id"]]
        res = retrieve_for_job(lab["persona_id"], job, cfg)
        latencies.append(res["latency_ms"])
        if res["per_requirement"]:
            share_none = np.mean([p["status"] == "none" for p in res["per_requirement"]])
            none_rate[lab["kind"]].append(share_none)
        if not lab["gold_evidence"]:
            continue                                   # poor-fit jobs: only used for the no-evidence rate
        ranked, gold = [i for i, _ in res["ranked"]], set(lab["gold_evidence"])
        rows.append({"job_id": lab["job_id"], "persona": lab["persona_id"], "style": lab["post_style"],
                     "recall@5": recall_at(ranked, gold, 5), "mrr": mrr(ranked, gold),
                     "ndcg@10": ndcg_at(ranked, gold)})
    by_persona = {p: summarise([r for r in rows if r["persona"] == p]) for p in sorted({r["persona"] for r in rows})}
    by_style = {s: summarise([r for r in rows if r["style"] == s]) for s in sorted({r["style"] for r in rows})}
    return {"config": cfg.__dict__, "overall": summarise(rows), "by_persona": by_persona, "by_style": by_style,
            "latency_ms": {"p50": round(float(np.percentile(latencies, 50)), 1),
                           "p95": round(float(np.percentile(latencies, 95)), 1)},
            "no_evidence_rate": {k: round(float(np.mean(v)), 3) for k, v in none_rate.items()
                                 if k in ("good", "poor_fit")},
            "per_job": rows}


def main():
    jobs = {j["job_id"]: j for j in json.loads((ROOT / "data/gigsim/jobs.json").read_text(encoding="utf-8"))}
    all_labels = json.loads((ROOT / "evals/datasets/dev_labels.json").read_text(encoding="utf-8"))
    # Jobs with gold evidence (good + injection) and poor-fit jobs; duplicates/scams/low-budget left out.
    labels = [lab for lab in all_labels if lab["kind"] in ("good", "injection", "poor_fit")]

    # Warm-up so model loading time is not counted as latency.
    retrieve_for_job("ml_engineer", next(iter(jobs.values())), get_config("v8_corrective"))

    results = {}
    for name in VARIANTS:
        print(f"running {name} ...")
        results[name] = evaluate(get_config(name), jobs, labels)

    # Pre-registered decision rule (evals/HYPOTHESES.md): ship the SIMPLEST variant within
    # 2 points of the best Recall@5, with p95 latency under 2 s.
    best = max(VARIANTS, key=lambda v: results[v]["overall"]["recall@5"])
    best_r = results[best]["overall"]["recall@5"]
    shipped = next(v for v in VARIANTS if results[v]["overall"]["recall@5"] >= best_r - 0.02
                   and results[v]["latency_ms"]["p95"] < 2000)

    # Ablation: remove one part at a time from the FULL pipeline (V8 has every part switched on;
    # if the winner is V0 it has no parts to remove, so we ablate the full stack instead).
    full_name = best if get_config(best).corrective else "v8_corrective"
    full_cfg, ablations = get_config(full_name), {}
    for part in ["decompose", "hybrid", "rerank", "corrective"]:
        print(f"ablation: {full_name} without {part} ...")
        r = evaluate(full_cfg.without(part), jobs, labels)
        ablations[f"{full_name} - {part}"] = {k: r[k] for k in ("overall", "latency_ms", "no_evidence_rate")}

    OUT.mkdir(parents=True, exist_ok=True)
    report = {"generated_at": time.strftime("%Y-%m-%d %H:%M"), "dataset": "evals/datasets/dev_labels.json",
              "n_jobs_with_gold": results["v0_naive"]["overall"]["n"], "best": best, "shipped": shipped,
              "decision_rule": "simplest variant within 0.02 Recall@5 of the best, p95 < 2000 ms",
              "variants": results, "ablations": ablations}
    (OUT / "rag_eval.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    header = ["variant", "recall@5", "mrr", "ndcg@10", "p50_ms", "p95_ms", "none_good", "none_poor_fit"]
    table = [[n, r["overall"]["recall@5"], r["overall"]["mrr"], r["overall"]["ndcg@10"], r["latency_ms"]["p50"],
              r["latency_ms"]["p95"], r["no_evidence_rate"].get("good", "-"), r["no_evidence_rate"].get("poor_fit", "-")]
             for n, r in list(results.items()) + list(ablations.items())]
    with (OUT / "rag_eval.csv").open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([header] + table)
    md = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)] + \
         ["| " + " | ".join(str(c) for c in row) + " |" for row in table]
    (OUT / "rag_table.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    print(f"\nbest = {best}, shipped (decision rule) = {shipped}")


if __name__ == "__main__":
    main()
