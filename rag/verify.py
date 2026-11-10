"""
verify.py - claim verification (B3): "did the writer tell the truth?"

In simple words:
    After the Writer drafts a proposal, we
      1. split it into sentences,
      2. keep the ones that CLAIM something about the freelancer's past
         ("I built...", "my model cut churn by 9%..."), skipping plans ("I would..."),
      3. check every claim against the evidence the Writer was given:
           - is there an evidence item that talks about the same thing?  (reranker score)
           - does every NUMBER in the claim appear in the evidence?      ("9%", "4 years")
           - does every TECH SKILL named in the claim appear in the evidence? ("Kubernetes")
      4. label it supported / partly_supported / unsupported,
      5. REMOVE unsupported claims before the Critic sees the draft.

    It needs no LLM, so it is free, fast and gives the same answer every time.
    (Viva: delete an evidence item and regenerate -> its claims become unsupported -> removed.)
"""

import json
import re
from functools import lru_cache
from pathlib import Path

from agent.settings import CONFIG
from rag import models

THRESHOLD = CONFIG["rag"]["verify_threshold"]
ROOT = Path(__file__).resolve().parents[1]

# A sentence is a "claim" if it is first-person AND about something done or had.
FIRST_PERSON = re.compile(r"\b(i|i've|i'm|my|me|we|our)\b", re.IGNORECASE)
PAST_OR_FACT = re.compile(
    r"\b(\w+ed|built|led|made|wrote|ran|cut|won|shipped|taught|grew|rebuilt|have|has|had|years?|"
    r"experience|delivered|worked|reached|saved)\b", re.IGNORECASE)
# A sentence is a PLAN only if it STARTS with a plan phrase. ("My 4 years of X ensure I can do Y"
# is still a claim about the past and must be checked.)
PLAN = re.compile(r"^\W*(then |next |so |and |first,? |for (you|your \w+),? )?(i would|i will|i'll|i can|i could|"
                  r"i'd|i'm happy|happy to|let's|i plan|i suggest|i'm available|i'm keen|could we|would you|"
                  r"shall we|my plan|the next step)\b", re.IGNORECASE)
NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


@lru_cache(maxsize=1)
def tech_vocabulary() -> set[str]:
    """Every skill name we know of (from all portfolios + all job ideas), lower-case."""
    vocab = set()
    for f in (ROOT / "data" / "personas").glob("*/portfolio.json"):
        for item in json.loads(f.read_text(encoding="utf-8"))["items"]:
            vocab |= {s.lower() for s in item["skills"]}
    ideas = json.loads((ROOT / "data" / "gigsim" / "job_ideas.json").read_text(encoding="utf-8"))
    for cat in ("ml", "web", "data"):
        for idea in ideas[cat]:
            vocab |= {s.lower() for s in idea["required_skills"]}
    # drop generic words that are "skills" in name only
    return {v for v in vocab if len(v) > 2} - {"communication", "documentation", "llm", "charts", "rag"}


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def is_claim(sentence: str) -> bool:
    if PLAN.search(sentence) or sentence.endswith("?"):
        return False
    return bool(FIRST_PERSON.search(sentence) and (PAST_OR_FACT.search(sentence) or NUMBER.search(sentence)))


def _terms_in(sentence: str) -> list[str]:
    low = sentence.lower()
    return [t for t in tech_vocabulary() if re.search(rf"(?<![\w-]){re.escape(t)}(?![\w-])", low)]


def check_claim(claim: str, evidence: list[dict]) -> dict:
    """Label one claim against the evidence items (each has id, text, skills, title)."""
    if not evidence:
        return {"text": claim, "label": "unsupported", "evidence_id": None, "score": None,
                "missing": ["no evidence given"]}
    texts = [f"{e['title']}. {e['text']} {' '.join(e.get('skills', []))}" for e in evidence]
    scores = models.rerank_scores(claim, texts)
    best = max(range(len(scores)), key=scores.__getitem__)
    all_text = " ".join(texts).lower()

    missing = [n for n in NUMBER.findall(claim) if n not in all_text]
    missing += [t for t in _terms_in(claim) if t not in all_text]
    matched_something = bool(NUMBER.findall(claim) or _terms_in(claim)) and \
        len(missing) < len(NUMBER.findall(claim)) + len(_terms_in(claim))

    if not missing and scores[best] >= THRESHOLD:
        label = "supported"
    elif (not missing and scores[best] >= THRESHOLD - 4) or (missing and matched_something and scores[best] >= THRESHOLD):
        label = "partly_supported"
    else:
        label = "unsupported"
    return {"text": claim, "label": label, "evidence_id": evidence[best]["id"],
            "score": round(scores[best], 3), "missing": missing}


def verify_claims(draft: str, evidence: list[dict]) -> dict:
    """
    Returns {
      "claims":            [{text, label, evidence_id, score, missing}],
      "unsupported_rate":  fraction of claims that are unsupported (before cleaning),
      "cleaned_draft":     the draft with unsupported claims removed,
      "removed":           the sentences that were removed
    }
    """
    results, removed, kept = [], [], []
    for sentence in split_sentences(draft):
        if is_claim(sentence):
            r = check_claim(sentence, evidence)
            results.append(r)
            if r["label"] == "unsupported":
                removed.append(sentence)
                continue
        kept.append(sentence)
    n = len(results)
    return {"claims": results,
            "unsupported_rate": round(sum(r["label"] == "unsupported" for r in results) / n, 3) if n else 0.0,
            "cleaned_draft": " ".join(kept), "removed": removed}
