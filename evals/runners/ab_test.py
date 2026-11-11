"""
ab_test.py - signature extension X2: two proposal strategies as an A/B test in GigSim.

    Strategy A (control): agent/prompts/writer.md   - problem-first, 1-2 pieces of evidence
    Strategy B (variant): agent/prompts/writer_b.md - short, opens with one sharp question

Both arms run the full bid graph on the same good-fit dev jobs; drafts are auto-approved
(eval only) and the simulated clients decide. We compare reply rates with a two-proportion
z-test (two-sided). Arm A's results come from the main decision eval.

    python -m evals.runners.ab_test     -> evals/results/ab_test.json
"""

import asyncio
import json
import math

from evals.runners import harness


def two_proportion_z(s1: int, n1: int, s2: int, n2: int) -> dict:
    """z-test for the difference between two reply rates."""
    p1, p2 = s1 / n1, s2 / n2
    p = (s1 + s2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2)) or 1e-9
    z = (p2 - p1) / se
    p_value = math.erfc(abs(z) / math.sqrt(2))           # two-sided
    return {"rate_a": round(p1, 3), "rate_b": round(p2, 3), "diff": round(p2 - p1, 3), "z": round(z, 3),
            "p_value": round(p_value, 4), "significant_at_0.05": p_value < 0.05}


if __name__ == "__main__":
    harness.setup(fake_llm=False, extra_env={"GIGBID_WRITER_PROMPT": "writer_b"})
    jobs, labels = harness.load_dev(kinds=("good",))
    arm_b = asyncio.run(harness.run(labels, jobs, user_suffix="-armb"))
    arm_a = [r for r in json.loads((harness.RESULTS / "decision_eval.json").read_text(encoding="utf-8"))["per_job"]
             if r["kind"] == "good"]

    def counts(rows):
        sent = [r for r in rows if r.get("proposal_id")]
        return sum(r.get("outcome") in ("replied", "interview", "hired") for r in sent), len(sent)

    sa, na = counts(arm_a)
    sb, nb = counts(arm_b)
    test = two_proportion_z(sa, na, sb, nb) if na and nb else None
    words = lambda rows: round(sum(len(r["draft"].split()) for r in rows if r.get("draft")) /
                               max(1, sum(bool(r.get("draft")) for r in rows)), 1)
    harness.save("ab_test", {
        "arm_a": {"prompt": "writer.md", "replied": sa, "sent": na, "avg_words": words(arm_a)},
        "arm_b": {"prompt": "writer_b.md", "replied": sb, "sent": nb, "avg_words": words(arm_b)},
        "test": test, "per_job_b": arm_b})
    print(test)
