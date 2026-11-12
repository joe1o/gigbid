"""
ablation.py - the RAG ablation on its own: start from the full pipeline (V8: decomposition, hybrid
BM25 + dense, reranker, corrective loop) and remove one part at a time.

    python -m evals.runners.ablation      -> evals/results/ablation.json

rag_eval.py runs the same ablation after scoring every variant; this runner repeats only that part
(CPU only, about a minute), using the same scoring code.
"""

import json
import time
from pathlib import Path

from evals.runners.rag_eval import evaluate
from rag.retriever import get_config

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "evals" / "results"


def main():
    jobs = {j["job_id"]: j for j in json.loads((ROOT / "data/gigsim/jobs.json").read_text(encoding="utf-8"))}
    labels = [lab for lab in json.loads((ROOT / "evals/datasets/dev_labels.json").read_text(encoding="utf-8"))
              if lab["kind"] in ("good", "injection", "poor_fit")]
    full = get_config("v8_corrective")
    rows = {"v8_corrective (full)": evaluate(full, jobs, labels)}
    for part in ["decompose", "hybrid", "rerank", "corrective"]:
        print(f"without {part} ...", flush=True)
        rows[f"v8_corrective - {part}"] = evaluate(full.without(part), jobs, labels)
    report = {"generated_at": time.strftime("%Y-%m-%d %H:%M"),
              "rows": {k: {x: r[x] for x in ("overall", "latency_ms", "no_evidence_rate")} for k, r in rows.items()}}
    (OUT / "ablation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    for k, r in report["rows"].items():
        print(f"{k:32} recall@5 {r['overall']['recall@5']:.3f}  mrr {r['overall']['mrr']:.3f}")


if __name__ == "__main__":
    main()
