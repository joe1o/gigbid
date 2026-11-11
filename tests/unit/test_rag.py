"""Tests for RAG building blocks: chunking, fusion, metrics, retrieval and claim verification."""

from evals.runners.rag_eval import mrr, ndcg_at, recall_at
from rag import corpus, retriever, verify
from rag.index.store import get_index
from rag.ingest.chunker import chunk_portfolio
from rag.pipeline import rrf


def test_chunks_keep_metadata():
    chunks = chunk_portfolio("ml_engineer")
    proposal = next(c for c in chunks if c["item_id"] == "ml-pp-churn-won")
    assert proposal["persona"] == "ml_engineer" and proposal["outcome"] == "won"
    assert {"type", "project", "skills", "date", "client_industry"} <= set(proposal)


def test_index_is_incremental():
    get_index("data_analyst")                         # builds (or loads) the cache
    from rag.index.store import PersonaIndex
    assert PersonaIndex("data_analyst").newly_embedded == 0   # nothing new -> nothing re-embedded


def test_rrf_rewards_items_high_in_any_list():
    fused = [k for k, _ in rrf([["a", "b", "c"], ["c", "a", "d"]])]
    assert fused[0] == "a" and set(fused) == {"a", "b", "c", "d"}


def test_metrics():
    gold = {"x", "y"}
    assert recall_at(["x", "q", "y"], gold, 2) == 0.5
    assert mrr(["q", "x"], gold) == 0.5
    assert ndcg_at(["x", "y"], gold) == 1.0


def test_shipped_retriever_finds_evidence():
    hits = retriever.search("web_developer", "Stripe checkout for an online store", k=3)
    assert "web-cs-shop" in [h["id"] for h in hits]


def test_corrective_refuses_skills_the_freelancer_lacks():
    job = {"title": "iOS app", "description": "Native SwiftUI app with HealthKit.",
           "required_skills": ["SwiftUI", "HealthKit"]}
    res = retriever.retrieve_for_job("ml_engineer", job, variant="v8_corrective")
    assert all(p["status"] == "none" for p in res["per_requirement"][:2])


def test_verify_keeps_true_claims_and_removes_invented_ones():
    ev = [corpus.get_item("ml_engineer", i) for i in ["ml-cs-churn", "ml-cv"]]
    draft = ("I built a churn model for a telecom operator and cut churn by 9% in one quarter. "
             "I have 10 years of experience with Kubernetes. I would start with a baseline.")
    r = verify.verify_claims(draft, ev)
    labels = [c["label"] for c in r["claims"]]
    assert labels == ["supported", "unsupported"]                 # the plan sentence is not a claim
    assert "Kubernetes" not in r["cleaned_draft"] and "baseline" in r["cleaned_draft"]


def test_verify_with_no_evidence_marks_claims_unsupported():
    r = verify.verify_claims("I built a churn model with 0.71 PR-AUC.", [])
    assert r["unsupported_rate"] == 1.0


def test_claim_inside_a_plan_sentence_is_still_checked():
    """Regression: 'my N years ... ensures I can ...' was skipped as a plan because of 'I can'."""
    ev = [corpus.get_item("ml_engineer", i) for i in ["ml-cv"]]
    fake = "Additionally, my ten years of experience with Kubernetes ensures I can scale it."
    assert verify.is_claim(fake) and verify.check_claim(fake, ev)["label"] == "unsupported"
    assert not verify.is_claim("My plan is to containerize the model with a Dockerfile.")


def test_requests_to_the_client_are_not_claims():
    """Regression (human labels P05/P12): closing requests were deleted as 'unsupported claims'."""
    s = ("Please share any preferred base image or deployment constraints so I can tailor the Docker setup, "
         "and let me know if you would like to discuss details over a quick call.")
    assert not verify.is_claim(s)


def test_unknown_tool_named_in_a_claim_is_caught():
    """Regression (human label P30): 'scipy' is not in the data analyst's portfolio."""
    ev = [corpus.get_item("data_analyst", "data-cv")]
    claim = "My CV shows strong Python (pandas, scipy) and SQL skills."
    r = verify.check_claim(claim, ev)
    assert "scipy" in r["missing"] and r["label"] != "supported"
