"""
gigsim_outcomes.py - what GigSim's simulated clients did with the proposals GigBid sent.

    python -m evals.runners.gigsim_outcomes     -> evals/results/gigsim_outcomes.json

decision_eval.py submits the approved proposals and records each client's response (viewed, replied,
interview, hired, lost) from GigSim. This runner turns those per-job outcomes into the funnel, overall,
by persona and by post style.
"""

import json
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "evals" / "results"
REPLIED = {"replied", "interview", "hired"}


def funnel(rows: list[dict]) -> dict:
    sent = [r for r in rows if r.get("outcome")]
    counts = Counter(r["outcome"] for r in sent)
    return {"proposals_sent": len(sent), "outcomes": dict(counts),
            "reply_rate": round(sum(counts[k] for k in REPLIED) / len(sent), 3) if sent else None}


def main():
    rows = json.loads((RESULTS / "decision_eval.json").read_text(encoding="utf-8"))["per_job"]
    report = {"generated_at": time.strftime("%Y-%m-%d %H:%M"), "source": "evals/results/decision_eval.json",
              "overall": funnel(rows),
              "by_persona": {p: funnel([r for r in rows if r["persona"] == p]) for p in sorted({r["persona"] for r in rows})},
              "by_style": {s: funnel([r for r in rows if r.get("style") == s]) for s in sorted({r.get("style") for r in rows})}}
    (RESULTS / "gigsim_outcomes.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
