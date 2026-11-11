"""
decision_eval.py - the main end-to-end evaluation on the dev set.

Every dev job goes through the full bid graph; drafts are auto-approved (eval only) and the
simulated clients react. Reports bid/skip F1, scam precision/recall, price inside the fair
band, unsupported claims before/after verification, reply and hire rate, latency and cost -
overall and per persona.

    python -m evals.runners.decision_eval                # real models (Groq), all dev jobs
    python -m evals.runners.decision_eval --fake --smoke # fake model, 30 jobs (CI smoke eval)
Writes evals/results/decision_eval[_smoke].json
"""

import argparse
import asyncio
import sys

from evals.runners import harness

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fake", action="store_true", help="use the fake LLM (free, deterministic)")
    ap.add_argument("--smoke", action="store_true", help="30 jobs only, and check the CI thresholds")
    ap.add_argument("--profile", default=None, help="model profile: open | open_small | paid")
    args = ap.parse_args()
    harness.setup(fake_llm=args.fake, extra_env={"MODEL_PROFILE": args.profile} if args.profile else None)

    jobs, labels = harness.load_dev(limit=30 if args.smoke else None)
    results = asyncio.run(harness.run(labels, jobs))
    m = harness.metrics(results, labels)
    by_persona = {p: harness.metrics([r for r in results if r["persona"] == p],
                                     [lab for lab in labels if lab["persona_id"] == p])
                  for p in sorted({r["persona"] for r in results})}
    name = "decision_eval_smoke" if args.smoke else f"decision_eval{'_' + args.profile if args.profile else ''}"
    harness.save(name, {"fake_llm": args.fake, "profile": args.profile or "open", "overall": m,
                        "by_persona": by_persona, "per_job": results})
    print({k: m[k] for k in ("bid_skip", "scam", "price_in_fair_band", "unsupported_claims_per_proposal", "reply_rate")})

    if args.smoke:                                   # CI gate: fail if quality drops past the thresholds
        import yaml

        th = yaml.safe_load((harness.ROOT / "evals" / "thresholds.yaml").read_text(encoding="utf-8"))
        problems = []
        if m["bid_skip"]["f1"] < th["min_bid_skip_f1"]:
            problems.append(f"bid/skip F1 {m['bid_skip']['f1']} < {th['min_bid_skip_f1']}")
        if (m["unsupported_claims_per_proposal"]["after"] or 0) > th["max_unsupported_claims_after"]:
            problems.append(f"unsupported claims after verification {m['unsupported_claims_per_proposal']['after']}")
        if m["scam"]["recall"] < th["min_scam_recall"]:
            problems.append(f"scam recall {m['scam']['recall']} < {th['min_scam_recall']}")
        if problems:
            print("SMOKE EVAL FAILED:", "; ".join(problems))
            sys.exit(1)
        print("smoke eval passed")
