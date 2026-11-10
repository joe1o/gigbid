"""
promotion_rules.py - WHEN something is allowed into long-term memory (requirement R7).

In simple words:
    GigBid does not "learn" from every single thing. A one-off edit might be a mood;
    one reply might be luck. So observations wait as CANDIDATES until a rule says they
    have earned their place. Only then are they PROMOTED to memory that the Writer uses.

    STYLE rule   : a style observation (e.g. "user deletes the word 'passionate'") is
                   promoted only after it shows up in at least 2 SEPARATE edits.
    OUTCOME rule : a category's outcome summary (reply rate, openings that worked) is
                   promoted only after at least 3 proposals in that category got a result.

Raw tool output never goes straight into memory: it must pass through these rules.
"""

import re

STYLE_MIN_EDITS = 2
OUTCOME_MIN_RESULTS = 3

STOPWORDS = {"a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "can", "could", "did", "do", "does", "for", "from", "had", "has", "have", "i", "if", "in", "into", "is", "it", "its", "just", "let", "me", "more", "my", "of", "on", "or", "our", "so", "than", "that", "the", "their", "them", "then", "there", "these", "they", "this", "to", "up", "us", "was", "we", "were", "what", "when", "which", "will", "with", "would", "you", "your", "about", "also", "very", "really", "all", "any", "some", "such", "here"}


def _first_sentence(text: str) -> str:
    return re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)[0].strip()


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z'-]{3,}", text.lower()) if w not in STOPWORDS}


def style_observations(original: str, edited: str) -> list[tuple[str, str]]:
    """Compare a draft with the user's edited version -> [(key, rule text), ...]."""
    obs = []
    first = _first_sentence(original)
    if first and first not in edited:
        obs.append(("cut_first_sentence",
                    "The user usually deletes the first sentence of drafts: open directly with the substance."))
    removed = sorted(_words(original) - _words(edited))
    for w in removed[:6]:
        obs.append((f"avoid_word:{w}", f'Do not use the word "{w}".'))
    n_orig, n_edit = len(original.split()), len(edited.split())
    if n_orig and n_edit < 0.8 * n_orig:
        obs.append(("shorter", f"Keep proposals short: about {round(n_edit, -1):.0f} words."))
    return obs


def should_promote_style(times_seen: int) -> bool:
    return times_seen >= STYLE_MIN_EDITS


def should_promote_outcome(results_in_category: int) -> bool:
    return results_in_category >= OUTCOME_MIN_RESULTS


def outcome_summary(events: list[dict]) -> dict:
    """events: [{outcome: replied|interview|hired|lost, cover_letter}] -> the memory value."""
    good = [e for e in events if e["outcome"] in ("replied", "interview", "hired")]
    return {
        "results": len(events),
        "reply_rate": round(len(good) / len(events), 2),
        "hire_rate": round(sum(e["outcome"] == "hired" for e in events) / len(events), 2),
        "openings_that_got_replies": [_first_sentence(e["cover_letter"]) for e in good][:3],
    }
