"""
store.py - long-term memory on top of the LangGraph store (a key-value database).

Namespaces (think "folders"):
    ("style", user)                   PROMOTED style rules            -> Writer reads these
    ("outcome", user, category)       PROMOTED outcome summary        -> Writer reads these
    ("style_candidates", user)        observations waiting for promotion
    ("style_edits", user)             each edit once (original + edited), for audit
    ("outcome_events", user, cat)     each proposal result once, waiting for promotion
    ("ledger", user)                  what we submitted (proposal id -> job, category, text)

Only the first two are "memory". Everything else is bookkeeping that feeds the
promotion rules in promotion_rules.py. The user can view and delete memories in the UI.
"""

import time

from agent.memory import promotion_rules as rules


async def record_edit(store, user: str, edit_id: str, original: str, edited: str) -> list[str]:
    """Save one user edit and update style candidates. Returns newly promoted rules. Idempotent per edit_id."""
    if await store.aget(("style_edits", user), edit_id):
        return []
    await store.aput(("style_edits", user), edit_id, {"original": original[:3000], "edited": edited[:3000],
                                                       "at": time.time()})
    promoted = []
    for key, rule_text in rules.style_observations(original, edited):
        cand = await store.aget(("style_candidates", user), key)
        seen = (cand.value["times_seen"] if cand else 0) + 1
        edits = ((cand.value["edits"] if cand else []) + [edit_id])[-5:]
        await store.aput(("style_candidates", user), key, {"rule": rule_text, "times_seen": seen, "edits": edits})
        if rules.should_promote_style(seen) and not await store.aget(("style", user), key):
            await store.aput(("style", user), key, {
                "rule": rule_text, "promoted_at": time.time(), "evidence_edits": edits,
                "promotion_rule": f"seen in {seen} separate edits (minimum {rules.STYLE_MIN_EDITS})"})
            promoted.append(rule_text)
    return promoted


async def style_rules(store, user: str) -> list[str]:
    return [i.value["rule"] for i in await store.asearch(("style", user), limit=50)]


async def record_outcome(store, user: str, proposal_id: str, category: str, cover_letter: str,
                         outcome: str) -> bool:
    """Save one proposal result; promote the category summary when the rule allows. Idempotent."""
    ns = ("outcome_events", user, category)
    old = await store.aget(ns, proposal_id)
    if old and old.value["outcome"] == outcome:
        return False
    await store.aput(ns, proposal_id, {"outcome": outcome, "cover_letter": cover_letter[:3000], "at": time.time()})
    events = [i.value for i in await store.asearch(ns, limit=500)]
    if rules.should_promote_outcome(len(events)):
        await store.aput(("outcome", user, category), "summary", {
            **rules.outcome_summary(events), "promoted_at": time.time(),
            "promotion_rule": f"{len(events)} results in '{category}' (minimum {rules.OUTCOME_MIN_RESULTS})"})
        return True
    return False


async def outcome_hints(store, user: str, category: str) -> str:
    item = await store.aget(("outcome", user, category), "summary")
    if not item:
        return "(not enough results yet)"
    v = item.value
    lines = [f"Reply rate so far in {category}: {v['reply_rate']:.0%} over {v['results']} proposals."]
    lines += [f'Opening that got a reply: "{o}"' for o in v["openings_that_got_replies"]]
    return "\n".join(lines)


async def list_memories(store, user: str) -> list[dict]:
    """Everything GigBid has learned about this user (for the Settings memory viewer)."""
    out = [{"namespace": "style", "key": i.key, **i.value} for i in await store.asearch(("style", user), limit=100)]
    for cat in ("ml", "web", "data"):
        item = await store.aget(("outcome", user, cat), "summary")
        if item:
            out.append({"namespace": f"outcome/{cat}", "key": "summary", **item.value})
    return out


async def delete_memory(store, user: str, namespace: str, key: str) -> None:
    """User deletes a memory. The candidate is reset too, so it must be re-earned."""
    if namespace == "style":
        await store.adelete(("style", user), key)
        await store.adelete(("style_candidates", user), key)
    elif namespace.startswith("outcome/"):
        await store.adelete(("outcome", user, namespace.split("/", 1)[1]), key)


async def sync_outcomes(store, user: str, mcp) -> int:
    """Read proposal statuses from the marketplace and feed finished ones to the outcome rule."""
    n = 0
    for p in await mcp.call("pipeline", "list_proposals"):
        if p["status"] not in ("replied", "interview", "hired", "lost"):
            continue
        led = await store.aget(("ledger", user), p["proposal_id"])
        if led:
            n += await record_outcome(store, user, p["proposal_id"], led.value["category"],
                                      led.value["cover_letter"], p["status"])
    return n
