"""
chunker.py - cuts each portfolio item into small overlapping pieces ("chunks").

In simple words:
    Search works better on short passages than on whole documents, so every item
    (CV, case study, README, code, review, past proposal) is cut into windows of
    ~40 words that overlap by 10 words (so a sentence on a boundary isn't lost).

    Every chunk keeps the item's METADATA, as the assignment requires:
    persona, type, project, skills, date, client industry and (for past
    proposals) outcome. Filters and the "outcome" signal rely on this.

Loaders: our corpus is already structured JSON (data/personas/*/portfolio.json),
one record per CV / case study / README / code file / review / proposal. Code and
READMEs from real GitHub repos would come in through the GitHub MCP server and be
saved in the same format (see docs/TOOLS.md).
"""

import hashlib

from agent.settings import CONFIG
from rag.corpus import load_portfolio

WORDS = CONFIG["rag"]["chunk_words"]
OVERLAP = CONFIG["rag"]["chunk_overlap"]
META_FIELDS = ["type", "project", "skills", "date", "client_industry", "outcome"]


def chunk_item(item: dict, persona_id: str) -> list[dict]:
    words = item["text"].split()
    step = WORDS - OVERLAP
    starts = range(0, max(len(words) - OVERLAP, 1), step)
    chunks = []
    for n, s in enumerate(starts):
        body = " ".join(words[s:s + WORDS])
        text = f"{item['title']}. {body}"            # the item title gives every chunk its context
        chunks.append({
            "chunk_id": f"{item['id']}#{n}",
            "item_id": item["id"],
            "text": text,
            "hash": hashlib.sha1(text.encode()).hexdigest(),   # used for incremental re-indexing
            "persona": persona_id,
            **{k: item.get(k) for k in META_FIELDS},
        })
    return chunks


def chunk_portfolio(persona_id: str) -> list[dict]:
    out = []
    for item in load_portfolio(persona_id)["items"]:
        out.extend(chunk_item(item, persona_id))
    return out
