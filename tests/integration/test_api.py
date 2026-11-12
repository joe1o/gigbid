"""
API smoke test: the whole backend through HTTP, like the browser uses it.
In-process servers + fake LLM + a throwaway SQLite database.
"""

import os
import tempfile
import time

import pytest

os.environ.update({"GIGBID_INPROCESS": "1", "GIGBID_TEST_MODE": "1",
                   "DATABASE_URL": "sqlite:///" + os.path.join(tempfile.mkdtemp(prefix="gigbid-api-"), "api.sqlite")})

from fastapi.testclient import TestClient

from apps.api.main import app
from gigsim import app as gigsim_app

REVIEWER = {"email": "reviewer@gigbid.app", "password": "review-local-only"}


@pytest.fixture(scope="module")
def client(monkeypatch_module=None):
    os.environ["GIGBID_FAKE_LLM"] = "1"
    from mcp_servers.marketplace import server as marketplace

    marketplace.limiter.per_minute = 10_000
    gigsim_app.RATE_LIMIT = 10_000
    TestClient(gigsim_app.app).post("/admin/reset", headers={"Authorization": "Bearer gigsim-admin-token"})
    with TestClient(app) as c:
        yield c
    os.environ.pop("GIGBID_FAKE_LLM", None)


def wait_for(client, job_id, statuses, timeout=60):
    t = time.time()
    while time.time() - t < timeout:
        s = client.get(f"/api/jobs/{job_id}").json()["summary"]["status"]
        if s in statuses:
            return s
        time.sleep(0.3)
    raise AssertionError(f"{job_id} stuck in {s}")


def test_requires_login(client):
    assert client.get("/api/jobs").status_code == 401


def test_full_flow(client):
    assert client.post("/api/auth/login", json=REVIEWER).status_code == 200
    me = client.get("/api/me").json()
    assert me["onboarded"] and me["gigsim"]["account"] == "ml_engineer"

    assert client.post("/api/scout").json()["new_jobs"] > 5
    jobs = client.get("/api/jobs").json()
    good = next(j for j in jobs if "Churn" in j["title"])
    assert wait_for(client, good["job_id"], {"awaiting_approval"}) == "awaiting_approval"

    detail = client.get(f"/api/jobs/{good['job_id']}").json()
    assert detail["approval"]["preview"]["connects_cost"] == good["connects_cost"] + gigsim_app.load_policy()["extra_connects_per_proposal"]
    assert detail["state"]["fit"]["matrix"]

    regen = client.post(f"/api/jobs/{good['job_id']}/regenerate", json={"paragraph_index": 1}).json()
    assert regen["paragraph"]

    assert client.post(f"/api/jobs/{good['job_id']}/decision", json={"action": "reject"}).status_code == 422
    client.post(f"/api/jobs/{good['job_id']}/decision", json={"action": "approve"})
    assert wait_for(client, good["job_id"], {"submitted"}) == "submitted"

    resp = client.get("/api/pipeline").json()
    cols = resp["columns"]
    assert sum(len(v) for k, v in cols.items() if k != "drafted") >= 1
    assert client.get("/api/analytics").json()["proposals_analysed"] >= 1
    assert client.get("/api/runs/" + detail["summary"]["thread_id"] + "/events").json()["events"]


def test_degraded_mode_health(client):
    client.post("/api/auth/login", json=REVIEWER)
    assert client.get("/api/health").json()["marketplace"] == "ok"
    client.post("/api/test/marketplace", params={"down": True})
    assert client.get("/api/health").json()["marketplace"] == "down"
    client.post("/api/test/marketplace", params={"down": False})
