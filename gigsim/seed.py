"""
seed.py - builds the fake marketplace's data from the hand-written job ideas.

In simple words:
    We wrote ~8 "job ideas" per freelancer type in data/gigsim/job_ideas.json.
    This script turns them into ~54 realistic job posts: two versions of each
    good idea (one detailed, one vague), plus scams, jobs with hidden
    "prompt injection" text, and duplicate reposts.

    It ALSO writes the answer key ("gold labels") for every job, e.g.
    "should the freelancer bid? is it a scam? which portfolio items prove fit?"
    The answer key goes to evals/datasets/dev_labels.json and is only used by our
    evaluation scripts. The marketplace never shows it to the agents.

Run:  python -m gigsim.seed
The random generator uses a fixed seed (42), so every run produces identical files.
"""

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # the gigbid/ repo folder
DATA = ROOT / "data" / "gigsim"
RNG = random.Random(42)                             # fixed seed = reproducible output

# Which persona (freelancer) owns which job category.
PERSONA_FOR = {"ml": "ml_engineer", "web": "web_developer", "data": "data_analyst"}

# Ordinary clients vs scam clients (ids from clients.json).
LEGIT_CLIENTS = [f"c{i:02d}" for i in range(1, 13)] + ["c15"]
SCAM_CLIENTS = ["c13", "c14"]


def connects_cost(budget_max: float) -> int:
    """Bigger jobs cost more Connects (bid credits) to apply to, like on Upwork."""
    if budget_max <= 100:
        return 2
    if budget_max < 500:
        return 4
    if budget_max < 1500:
        return 8
    if budget_max < 3000:
        return 12
    return 16


def round10(x: float) -> int:
    """Round a dollar amount to the nearest $10 so budgets look human-written."""
    return int(round(x / 10.0) * 10)


def make_job(category, title, description, skills, budget, questions, client_id):
    """Build one public job post (what the marketplace API returns)."""
    return {
        "title": title,
        "description": description,
        "required_skills": skills,
        "category": category,
        "budget": {"type": "fixed", "min": budget[0], "max": budget[1], "currency": "USD"},
        "duration_days": RNG.choice([7, 14, 21, 30]),
        "screening_questions": questions,
        "client_id": client_id,
        "connects_cost": connects_cost(budget[1]),
        # Most jobs are visible at start; the rest "arrive" later to simulate a live feed.
        "release_after_minutes": 0 if RNG.random() < 0.6 else RNG.choice([10, 30, 60, 120, 180]),
    }


def label(kind, idea, category, should_bid, **extra):
    """Build the answer-key entry for one job."""
    return {
        "persona_id": PERSONA_FOR[category],
        "category": category,
        "kind": kind,                         # good | poor_fit | low_budget | scam | injection | duplicate
        "idea_key": idea.get("key") if idea else None,
        "should_bid": should_bid,
        "is_scam": kind == "scam",
        "has_injection": kind == "injection",
        "duplicate_of": extra.get("duplicate_of"),
        "gold_evidence": idea.get("gold_evidence", []) if idea else [],
        "fair_band": idea.get("fair_band") if idea else None,
        "post_style": extra.get("style", "detailed"),   # detailed | vague (for results by job type)
    }


def build():
    ideas = json.loads((DATA / "job_ideas.json").read_text(encoding="utf-8"))
    pairs = []  # list of (job, label) before ids are assigned

    for cat in ["ml", "web", "data"]:
        cat_pairs = []
        goods = [i for i in ideas[cat] if i["kind"] == "good"]

        for idea in ideas[cat]:
            lo, hi = idea["fair_band"]
            if idea["kind"] == "good":
                # Version A: detailed post, budget inside the fair band.
                cat_pairs.append((
                    make_job(cat, idea["title"], idea["description"], idea["required_skills"],
                             (lo, hi), idea["screening_questions"], RNG.choice(LEGIT_CLIENTS)),
                    label("good", idea, cat, True),
                ))
                # Version B: vague post, fewer listed skills, budget a bit off the band.
                b = (round10(lo * RNG.uniform(0.8, 1.0)), round10(hi * RNG.uniform(0.9, 1.1)))
                cat_pairs.append((
                    make_job(cat, idea["title"], idea["vague_description"], idea["required_skills"][:2],
                             b, idea["screening_questions"], RNG.choice(LEGIT_CLIENTS)),
                    label("good", idea, cat, True, style="vague"),
                ))
            else:
                # poor_fit (skills the persona lacks) or low_budget (budget far too small)
                budget = tuple(idea.get("budget_override", (lo, hi)))
                cat_pairs.append((
                    make_job(cat, idea["title"], idea["description"], idea["required_skills"],
                             budget, idea["screening_questions"], RNG.choice(LEGIT_CLIENTS)),
                    label(idea["kind"], idea, cat, False),
                ))

        # Two scam posts per category (unpaid "test" work, off-platform crypto payment).
        thing = ideas["scam_things"][cat]
        for tmpl, client, budget in zip(ideas["scam_templates"], SCAM_CLIENTS, [(0, 50), (500, 500)]):
            cat_pairs.append((
                make_job(cat, tmpl["title"].format(thing=thing), tmpl["description"].format(thing=thing),
                         ["Python"] if cat != "web" else ["React"], budget, [], client),
                label("scam", None, cat, False),
            ))

        # Two legit jobs with planted prompt-injection text (the job itself is fine to bid on).
        for idea, inj in zip(goods[1:3], ideas["injection_texts"]):
            cat_pairs.append((
                make_job(cat, idea["title"], idea["description"] + inj, idea["required_skills"],
                         tuple(idea["fair_band"]), idea["screening_questions"], RNG.choice(LEGIT_CLIENTS)),
                label("injection", idea, cat, True),
            ))

        RNG.shuffle(cat_pairs)  # so the job id never hints at the job type
        pairs.extend(cat_pairs)

    # Give every job an id, then add one duplicate repost per category.
    jobs, labels = [], []
    for n, (job, lab) in enumerate(pairs, start=1):
        job_id = f"job-{n:03d}"
        jobs.append({"job_id": job_id, **job})
        labels.append({"job_id": job_id, **lab})

    for cat in ["ml", "web", "data"]:
        original = next(j for j, lab in zip(jobs, labels) if j["category"] == cat and lab["kind"] == "good")
        dup = dict(original, job_id=f"job-{len(jobs) + 1:03d}", release_after_minutes=30)
        orig_label = next(lab for lab in labels if lab["job_id"] == original["job_id"])
        jobs.append(dup)
        labels.append({**orig_label, "job_id": dup["job_id"], "kind": "duplicate",
                       "should_bid": False, "duplicate_of": original["job_id"]})

    # "Historical" budgets for price statistics (the Pricing agent uses these).
    medians = {"ml": 1000, "web": 1200, "data": 600}
    history = {cat: sorted(round10(RNG.lognormvariate(0, 0.55) * m) for _ in range(150))
               for cat, m in medians.items()}

    # Write everything to disk.
    (DATA / "jobs.json").write_text(json.dumps(jobs, indent=2), encoding="utf-8")
    (DATA / "market_history.json").write_text(json.dumps(history), encoding="utf-8")
    out = ROOT / "evals" / "datasets"
    out.mkdir(parents=True, exist_ok=True)
    (out / "dev_labels.json").write_text(json.dumps(labels, indent=2), encoding="utf-8")
    print(f"wrote {len(jobs)} jobs, {len(labels)} labels, market history for {len(history)} categories")


if __name__ == "__main__":
    build()
