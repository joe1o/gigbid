"""
change_request.py - measures how GigBid absorbs the platform policy update.

The assignment announces a "platform policy update" (a new rule or cost) released during the
assignment. The course's GigSim was not available, so we simulate one dated 2 Nov 2026:
    - every proposal costs 2 extra Connects
    - every proposal must disclose AI assistance with a fixed statement
It is applied by editing gigsim/policy.yaml ONLY. This script runs one good-fit job per persona
under the new policy and checks that the system obeys it without any code change:
    - the dry-run preview charges job Connects + 2
    - the final proposal contains the required statement (added by Compliance if the Writer forgot)

    python -m evals.runners.change_request   -> evals/results/change_request.json
"""

import asyncio
import subprocess

import yaml

from evals.runners import harness

if __name__ == "__main__":
    harness.setup(fake_llm=False)
    policy = yaml.safe_load((harness.ROOT / "gigsim" / "policy.yaml").read_text(encoding="utf-8"))
    jobs, labels = harness.load_dev(kinds=("good",))
    picked = [next(lab for lab in labels if lab["persona_id"] == p and lab["post_style"] == "detailed")
              for p in ("ml_engineer", "web_developer", "data_analyst")]
    results = asyncio.run(harness.run(picked, jobs, approve=False, user_suffix="-policy-v2"))
    statements = policy.get("required_statements", [])
    checks = []
    for r in results:
        job = jobs[r["job_id"]]
        checks.append({"job_id": r["job_id"], "status": r["status"],
                       "job_connects": job["connects_cost"], "charged_connects": r.get("connects_cost_preview"),
                       "extra_cost_applied": r.get("connects_cost_preview") == job["connects_cost"] + policy["extra_connects_per_proposal"],
                       "statement_present": all(s.lower() in (r.get("draft") or "").lower() for s in statements),
                       "writer_included_it_itself": all(s.lower() in (r.get("draft_raw") or "").lower() for s in statements)})
    diff = subprocess.run(["git", "diff", "--numstat", "HEAD~1", "--", "gigsim/policy.yaml"], cwd=harness.ROOT,
                          capture_output=True, text=True, check=False).stdout.strip()
    code_changes = subprocess.run(["git", "diff", "--stat", "HEAD~1", "--", "agent", "mcp_servers", "apps", "rag"],
                                  cwd=harness.ROOT, capture_output=True, text=True, check=False).stdout.strip()
    harness.save("change_request", {
        "policy_version": policy["version"], "extra_connects_per_proposal": policy["extra_connects_per_proposal"],
        "required_statements": statements, "policy_file_diff_numstat": diff,
        "code_files_changed": code_changes or "none", "checks": checks, "per_job": results})
    print(checks)
