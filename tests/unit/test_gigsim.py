"""
Tests for GigSim (our marketplace simulator).
FastAPI's TestClient calls the API in-process, so no server needs to be running.
"""

import os
import tempfile

# Test settings MUST be set before gigsim.app is imported (it reads them at import time).
os.environ["GIGSIM_ERROR_RATE"] = "0"           # no random 503s in tests
os.environ["GIGSIM_REVEAL_SECONDS"] = "0"       # clients react instantly
os.environ["GIGSIM_RELEASE_ALL"] = "true"       # every job visible
os.environ["GIGSIM_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.sqlite")

import pytest
from fastapi.testclient import TestClient

from gigsim import app as gigsim_app

client = TestClient(gigsim_app.app)
ML = {"Authorization": "Bearer gigsim-ml-token"}
ADMIN = {"Authorization": "Bearer gigsim-admin-token"}

GOOD_LETTER = (
    "Churn on imbalanced data is where most models fail, so I would start there. For a telecom "
    "client I built a scikit-learn and XGBoost churn model on 120k subscribers with 6% churn, "
    "judged it on PR-AUC and helped cut churn by 9% in one quarter. For you I would compare two "
    "Python models, report precision and recall at the top decile, and hand over a reproducible "
    "pipeline with a short limitations note. I can start this week and share a first baseline "
    "within five days so you can see real numbers early."
)


@pytest.fixture(autouse=True)
def fresh_market():
    """Every test starts from an empty marketplace."""
    client.post("/admin/reset", headers=ADMIN)


def first_job(category="ml") -> dict:
    return client.get("/jobs", params={"category": category, "q": "churn"}, headers=ML).json()[0]


def test_health():
    assert client.get("/health").json()["ok"] is True


def test_requires_token():
    assert client.get("/jobs").status_code == 401


def test_jobs_hide_internal_fields():
    jobs = client.get("/jobs", params={"limit": 100}, headers=ML).json()
    assert len(jobs) > 10
    assert all("release_after_minutes" not in j and "should_bid" not in j for j in jobs)


def test_client_history_hides_preferences():
    c = client.get("/clients/c01", headers=ML).json()
    assert c["total_spent_usd"] > 0 and "hidden" not in c


def test_dry_run_spends_nothing():
    job = first_job()
    body = {"job_id": job["job_id"], "cover_letter": GOOD_LETTER, "bid_amount": 600}
    preview = client.post("/proposals", params={"dry_run": True}, json=body, headers=ML).json()
    assert preview["dry_run"] is True and preview["connects_cost"] == job["connects_cost"]
    assert client.get("/me/connects", headers=ML).json()["balance"] == 100


def test_idempotency_key_prevents_double_submit():
    job = first_job()
    body = {"job_id": job["job_id"], "cover_letter": GOOD_LETTER, "bid_amount": 600}
    h = ML | {"Idempotency-Key": "abc-123"}
    first = client.post("/proposals", json=body, headers=h).json()
    second = client.post("/proposals", json=body, headers=h).json()      # a retry
    assert first["proposal_id"] == second["proposal_id"]
    assert client.get("/me/connects", headers=ML).json()["balance"] == 100 - job["connects_cost"]


def test_write_needs_idempotency_key():
    body = {"job_id": first_job()["job_id"], "cover_letter": GOOD_LETTER, "bid_amount": 600}
    assert client.post("/proposals", json=body, headers=ML).status_code == 400


def test_contact_details_get_no_reply():
    body = {"job_id": first_job()["job_id"], "bid_amount": 600,
            "cover_letter": GOOD_LETTER + " Email me at sara@example.com."}
    pid = client.post("/proposals", json=body, headers=ML | {"Idempotency-Key": "k1"}).json()["proposal_id"]
    assert client.get(f"/proposals/{pid}", headers=ML).json()["status"] == "lost"


def test_conversation_flow():
    """Submit to many good jobs; at least one client replies, and replying moves the thread on."""
    jobs = client.get("/jobs", params={"category": "ml", "limit": 100}, headers=ML).json()
    for i, job in enumerate(jobs[:8]):
        body = {"job_id": job["job_id"], "cover_letter": GOOD_LETTER + " " + " ".join(job["required_skills"]),
                "bid_amount": job["budget"]["min"]}
        client.post("/proposals", json=body, headers=ML | {"Idempotency-Key": f"flow-{i}"})
    threads = client.get("/threads", headers=ML).json()
    assert threads, "expected at least one client reply"
    t = threads[0]["thread_id"]
    client.post(f"/threads/{t}/messages", json={"text": "Happy to talk. Tuesday 3pm or Wednesday 11am?"},
                headers=ML | {"Idempotency-Key": "m1"})
    msgs = client.get(f"/threads/{t}/messages", headers=ML).json()
    assert [m["sender"] for m in msgs][-2:] == ["freelancer", "client"]


def test_rate_limit(monkeypatch):
    monkeypatch.setattr(gigsim_app, "RATE_LIMIT", 3)
    codes = [client.get("/jobs", headers=ML).status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200] and codes[-1] == 429
