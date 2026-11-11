"""
harness.py - the shared machinery every evaluation uses.

In simple words:
    It runs dev jobs through the REAL bid graph (real MCP servers in-process, real GigSim,
    real or fake LLM), auto-approves the drafts (evaluation only - in the app a human
    approves), lets the simulated clients react, and collects everything we measure:

    decisions  : bid/skip F1, scam precision/recall, price inside the fair band
    proposals  : unsupported claims per proposal before and after verification
    outcome    : GigSim reply rate and hire rate
    cost/speed : tokens, USD, p50/p95 seconds per job and per proposal

Usage from a runner:
    from evals.runners import harness
    harness.setup(fake_llm=False)          # MUST be called before other GigBid imports
    results = asyncio.run(harness.run(labels))
    print(harness.metrics(results))
"""

import asyncio
import json
import os
import statistics
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "evals" / "results"


def setup(fake_llm: bool, extra_env: dict | None = None) -> str:
    """Fresh throwaway databases + simulator settings for a repeatable run. Returns the temp dir."""
    tmp = tempfile.mkdtemp(prefix="gigbid-eval-")
    os.environ.update({
        "GIGSIM_RELEASE_ALL": "true", "GIGSIM_REVEAL_SECONDS": "0", "GIGSIM_ERROR_RATE": "0",
        "GIGSIM_DB_PATH": f"{tmp}/gigsim.sqlite", "MARKETPLACE_MCP_DB": f"{tmp}/marketplace.sqlite",
        "WORKSPACE_DB": f"{tmp}/workspace.sqlite", "DATABASE_URL": f"sqlite:///{tmp}/graph.sqlite",
        "GIGBID_SCHEDULER": "0", "LANGSMITH_TRACING": os.getenv("EVAL_TRACING", "false"),
    })
    if fake_llm:
        os.environ["GIGBID_FAKE_LLM"] = "1"
    os.environ.update(extra_env or {})
    from apps.api.inprocess import wire
    from gigsim import app as gigsim_app
    from mcp_servers.marketplace import server as marketplace

    wire()
    gigsim_app.RATE_LIMIT = 10_000              # the eval is a batch job, not a person clicking
    marketplace.limiter.per_minute = 10_000
    return tmp


def load_dev(kinds: tuple[str, ...] | None = None, personas: tuple[str, ...] | None = None, limit: int | None = None):
    jobs = {j["job_id"]: j for j in json.loads((ROOT / "data/gigsim/jobs.json").read_text(encoding="utf-8"))}
    labels = json.loads((ROOT / "evals/datasets/dev_labels.json").read_text(encoding="utf-8"))
    labels = [lab for lab in labels if lab["kind"] != "duplicate"]          # the Scout drops those before the graph
    if kinds:
        labels = [lab for lab in labels if lab["kind"] in kinds]
    if personas:
        labels = [lab for lab in labels if lab["persona_id"] in personas]
    return jobs, labels[:limit] if limit else labels


async def run(labels: list[dict], jobs: dict, approve: bool = True, concurrency: int = 2,
              settings_patch: dict | None = None, user_suffix: str = "") -> list[dict]:
    """Run each labelled job through the bid graph; return one result dict per job."""
    from agent import runtime as R
    from rag.verify import verify_claims

    sem = asyncio.Semaphore(concurrency)
    out = []
    async with R.open_runtime() as rt:
        async def one(lab):
            persona = lab["persona_id"]
            user = persona + user_suffix
            settings = {**R.default_settings(persona), **(settings_patch or {})}
            job = jobs[lab["job_id"]]
            async with sem:
                t0 = time.perf_counter()
                snap = await R.start_bid(rt, user, job, settings)
                v = snap["values"]
                res = {"job_id": job["job_id"], "persona": persona, "kind": lab["kind"],
                       "style": lab.get("post_style", "detailed"), "status": snap["status"],
                       "action": (v.get("decision") or {}).get("action"),
                       "risk_level": (v.get("risk") or {}).get("level"),
                       "risk_flags": (v.get("risk") or {}).get("flags", []),
                       "price": (v.get("price") or {}).get("amount"), "error": v.get("error")}
                if snap["interrupt"]:
                    claims = v["claims"]["claims"]
                    final = v["draft"]["cover_letter"] + " " + " ".join(v["draft"]["screening_answers"])
                    after = await asyncio.to_thread(verify_claims, final, v["evidence"])
                    res.update(draft_raw=v["draft_raw"]["cover_letter"], draft=v["draft"]["cover_letter"],
                               answers=v["draft"]["screening_answers"], evidence=v["evidence"],
                               claims=len(claims),
                               unsupported_before=sum(c["label"] == "unsupported" for c in claims),
                               unsupported_after=sum(c["label"] == "unsupported" for c in after["claims"]),
                               critic_rounds=len(v.get("critiques", [])),
                               compliance_fixes=len((v.get("compliance") or {}).get("fixes", [])))
                    if approve:
                        snap = await R.resume_bid(rt, user, job["job_id"], {"action": "approve"}, settings)
                        res["proposal_id"] = (snap["values"].get("submission") or {}).get("proposal_id")
                        res["status"] = snap["status"]
                usage = snap["values"].get("usage", [])
                res.update(seconds=round(time.perf_counter() - t0, 2),
                           tokens=sum(u["input_tokens"] + u["output_tokens"] for u in usage),
                           cost_usd=sum(u["cost_usd"] for u in usage))
                out.append(res)
                print(f"  {job['job_id']} {persona:14} {res['status']:18} {res['seconds']:6.1f}s {res['tokens']:6} tok",
                      flush=True)

        await asyncio.gather(*(one(lab) for lab in labels))
    await attach_outcomes(out)
    return out


async def attach_outcomes(results: list[dict]) -> None:
    """Ask GigSim what each submitted proposal's client did (replied / interview / hired / lost)."""
    from agent.mcp_client import GigBidMCP

    by_persona = {}
    for r in results:
        if r.get("proposal_id"):
            by_persona.setdefault(r["persona"], []).append(r)
    for persona, rows in by_persona.items():
        props = {p["proposal_id"]: p["status"]
                 for p in await GigBidMCP(persona, persona=persona).call("pipeline", "list_proposals")}
        for r in rows:
            r["outcome"] = props.get(r["proposal_id"])


def _pct(xs, q):
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, round(q * (len(xs) - 1)))], 2) if xs else None


def metrics(results: list[dict], labels: list[dict]) -> dict:
    lab = {x["job_id"]: x for x in labels}
    tp = sum(r["action"] == "bid" and lab[r["job_id"]]["should_bid"] for r in results)
    fp = sum(r["action"] == "bid" and not lab[r["job_id"]]["should_bid"] for r in results)
    fn = sum(r["action"] != "bid" and lab[r["job_id"]]["should_bid"] for r in results)
    correct = sum((r["action"] == "bid") == lab[r["job_id"]]["should_bid"] for r in results)
    p = tp / (tp + fp) if tp + fp else 0.0
    rc = tp / (tp + fn) if tp + fn else 0.0
    s_tp = sum(r["risk_level"] == "high" and lab[r["job_id"]]["is_scam"] for r in results)
    s_fp = sum(r["risk_level"] == "high" and not lab[r["job_id"]]["is_scam"] for r in results)
    s_fn = sum(r["risk_level"] != "high" and lab[r["job_id"]]["is_scam"] for r in results)
    priced = [r for r in results if r.get("price") and lab[r["job_id"]].get("fair_band") and r["action"] == "bid"]
    in_band = sum(lab[r["job_id"]]["fair_band"][0] <= r["price"] <= lab[r["job_id"]]["fair_band"][1] for r in priced)
    drafted = [r for r in results if "draft" in r]
    sent = [r for r in results if r.get("proposal_id")]
    replied = [r for r in sent if r.get("outcome") in ("replied", "interview", "hired")]
    return {
        "n_jobs": len(results),
        "bid_skip": {"accuracy": round(correct / len(results), 3), "precision": round(p, 3), "recall": round(rc, 3),
                     "f1": round(2 * p * rc / (p + rc), 3) if p + rc else 0.0},
        "scam": {"precision": round(s_tp / (s_tp + s_fp), 3) if s_tp + s_fp else 0.0,
                 "recall": round(s_tp / (s_tp + s_fn), 3) if s_tp + s_fn else 0.0},
        "price_in_fair_band": round(in_band / len(priced), 3) if priced else None,
        "proposals": len(drafted),
        "unsupported_claims_per_proposal": {
            "before": round(statistics.mean(r["unsupported_before"] for r in drafted), 3) if drafted else None,
            "after": round(statistics.mean(r["unsupported_after"] for r in drafted), 3) if drafted else None},
        "claims_per_proposal": round(statistics.mean(r["claims"] for r in drafted), 2) if drafted else None,
        "reply_rate": round(len(replied) / len(sent), 3) if sent else None,
        "hire_rate": round(sum(r.get("outcome") == "hired" for r in sent) / len(sent), 3) if sent else None,
        "seconds_per_job": {"p50": _pct([r["seconds"] for r in results], .5), "p95": _pct([r["seconds"] for r in results], .95)},
        "seconds_per_proposal": {"p50": _pct([r["seconds"] for r in drafted], .5),
                                 "p95": _pct([r["seconds"] for r in drafted], .95)},
        "tokens_per_job": round(statistics.mean(r["tokens"] for r in results)) if results else 0,
        "cost_usd_per_job": round(statistics.mean(r["cost_usd"] for r in results), 6) if results else 0,
        "cost_usd_per_proposal": round(statistics.mean(r["cost_usd"] for r in drafted), 6) if drafted else 0,
        "errors": [f"{r['job_id']}: {r['error']}" for r in results if r["status"] in ("dead_letter", "error")],
    }


def save(name: str, payload: dict) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / f"{name}.json"
    path.write_text(json.dumps({"generated_at": time.strftime("%Y-%m-%d %H:%M"), **payload}, indent=2, default=str),
                    encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}")
    return path
