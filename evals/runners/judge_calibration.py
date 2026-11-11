"""
judge_calibration.py - an LLM judge for proposal quality, CALIBRATED against a human.

An LLM judge is only trustworthy if it agrees with a person. So:
  1. --make-sheet : builds 30 proposals (real drafts from the decision eval, a few raw drafts
                    before verification, and a few deliberately weak generic ones) and writes
                    evals/datasets/judge_labels.csv for YOU to label: 1 = would send, 0 = would not.
  2. --score      : the judge (gpt-oss-120b, prompt agent/prompts/judge.md) grades the same 30;
                    we report Cohen's kappa between your labels and the judge, plus the judge's
                    average score for GigBid's real proposals (the "Judge score" in the results table).

Cohen's kappa = agreement corrected for chance: 1 = perfect, 0 = no better than chance.
"""

import argparse
import asyncio
import csv
import json
import random

from pydantic import BaseModel, Field

from evals.runners import harness

SHEET = harness.ROOT / "evals" / "datasets" / "judge_labels.csv"
ITEMS = harness.ROOT / "evals" / "datasets" / "judge_items.json"
GENERIC = ("Dear Sir, I am passionate about this kind of work and I have read your job carefully. I am the best fit "
           "for this job and have many years of experience. I guarantee high quality work delivered on time. "
           "Please message me so we can discuss the details.")


class Verdict(BaseModel):
    score: int = Field(ge=1, le=5)
    would_send: bool
    reason: str


def make_sheet() -> None:
    per_job = json.loads((harness.RESULTS / "decision_eval.json").read_text(encoding="utf-8"))["per_job"]
    jobs = {j["job_id"]: j for j in json.loads((harness.ROOT / "data/gigsim/jobs.json").read_text(encoding="utf-8"))}
    drafted = [r for r in per_job if r.get("draft")]
    rnd = random.Random(7)
    rnd.shuffle(drafted)
    items = []
    for r in drafted[:22]:
        items.append({"source": "gigbid_final", "job_id": r["job_id"], "persona": r["persona"],
                      "proposal": r["draft"], "evidence": r["evidence"]})
    for r in [x for x in drafted if x.get("unsupported_before")][:4] or drafted[22:26]:
        items.append({"source": "writer_raw_before_verification", "job_id": r["job_id"], "persona": r["persona"],
                      "proposal": r["draft_raw"], "evidence": r["evidence"]})
    for r in drafted[26:30] or drafted[:4]:
        items.append({"source": "generic_control", "job_id": r["job_id"], "persona": r["persona"],
                      "proposal": GENERIC, "evidence": r["evidence"]})
    rnd.shuffle(items)
    items = items[:30]
    for i, it in enumerate(items, start=1):
        it["id"] = f"P{i:02d}"
        it["job_title"] = jobs[it["job_id"]]["title"]
    ITEMS.write_text(json.dumps(items, indent=1), encoding="utf-8")
    with SHEET.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "job_title", "proposal", "your_label (1 = would send, 0 = would not)"])
        for it in items:
            w.writerow([it["id"], it["job_title"], it["proposal"], ""])
    print(f"wrote {SHEET} - fill the last column with 1 or 0, then run --score")


def cohen_kappa(a: list[int], b: list[int]) -> float:
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pa1, pb1 = sum(a) / n, sum(b) / n
    pe = pa1 * pb1 + (1 - pa1) * (1 - pb1)
    return round((po - pe) / (1 - pe), 3) if pe < 1 else 1.0


async def judge_all(items: list[dict]) -> list[dict]:
    from agent import llm
    from agent.nodes.writer import evidence_block

    jobs = {j["job_id"]: j for j in json.loads((harness.ROOT / "data/gigsim/jobs.json").read_text(encoding="utf-8"))}
    out = []
    for it in items:
        job = jobs[it["job_id"]]
        v, _usage = await llm.structured("critic", "judge", Verdict, job=f"{job['title']}\n{job['description']}",
                                        evidence=evidence_block(it["evidence"]), proposal=it["proposal"])
        out.append({"id": it["id"], "source": it["source"], **v.model_dump()})
        print(f"  {it['id']} {it['source']:32} score {v.score} send {v.would_send}", flush=True)
    return out


def score() -> None:
    items = json.loads(ITEMS.read_text(encoding="utf-8"))
    with SHEET.open(encoding="utf-8") as f:
        rows = list(csv.reader(f))[1:]
    human = {r[0]: int(r[3]) for r in rows if r[3].strip() in ("0", "1")}
    verdicts = asyncio.run(judge_all(items))
    labelled = [v for v in verdicts if v["id"] in human]
    kappa = cohen_kappa([human[v["id"]] for v in labelled], [int(v["would_send"]) for v in labelled]) if labelled else None
    agree = sum(human[v["id"]] == int(v["would_send"]) for v in labelled)
    ours = [v["score"] for v in verdicts if v["source"] == "gigbid_final"]
    disagreements = [{**v, "human": human[v["id"]]} for v in labelled if human[v["id"]] != int(v["would_send"])]
    harness.save("judge_calibration", {
        "n_labelled": len(labelled), "cohen_kappa": kappa, "raw_agreement": f"{agree}/{len(labelled)}",
        "judge_mean_score_gigbid_final": round(sum(ours) / len(ours), 2) if ours else None,
        "judge_mean_score_by_source": {s: round(sum(v["score"] for v in verdicts if v["source"] == s) /
                                                max(1, sum(v["source"] == s for v in verdicts)), 2)
                                       for s in {v["source"] for v in verdicts}},
        "disagreements": disagreements, "verdicts": verdicts})
    print(f"kappa={kappa} agreement={agree}/{len(labelled)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--make-sheet", action="store_true")
    ap.add_argument("--score", action="store_true")
    a = ap.parse_args()
    if a.make_sheet:
        make_sheet()
    if a.score:
        harness.setup(fake_llm=False)
        score()
