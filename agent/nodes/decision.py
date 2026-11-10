"""
Decision node - bid, watch or skip? Pure rules, so every decision is explainable.

    high risk                      -> skip   (never overridden)
    budget below the user's floor  -> skip
    fit < watch threshold (0.40)   -> skip
    fit < minimum (0.60)           -> watch
    otherwise                      -> bid
    "Draft anyway" (force_bid) turns skip/watch into bid, except for high risk.

Autonomy: with autonomy "auto_skip" a skip is filed away automatically; with "manual"
(default) it is only a recommendation the user sees in the inbox. Nothing is ever sent
without approval, whatever the autonomy setting.
"""

from agent.handoffs import BidDecision
from agent.nodes.base import node, user_settings
from agent.settings import CONFIG

TH = CONFIG["thresholds"]


@node("decide")
async def decide(state, config):
    risk, fit, job = state["risk"], state["fit"], state["job"]
    floor = user_settings(config).get("fixed_floor_usd", 0)
    reasons = [f"fit {fit['score']:.2f}", f"risk {risk['level']} ({risk['score']:.2f})"]

    if risk["level"] == "high":
        action = "skip"
        reasons.append("high risk: " + ", ".join(risk["flags"]))
    elif job["budget"]["max"] < floor:
        action = "skip"
        reasons.append(f"budget ${job['budget']['max']:.0f} is below your floor ${floor:.0f}")
    elif fit["score"] < TH["watch_fit_score"]:
        action = "skip"
        reasons.append("weak fit: " + "; ".join(fit["reasons"]))
    elif fit["score"] < TH["minimum_fit_score"]:
        action = "watch"
        reasons.append("borderline fit: " + "; ".join(fit["reasons"]))
    else:
        action = "bid"
        reasons.append("good fit and acceptable risk")

    if state.get("force_bid") and action != "bid" and risk["level"] != "high":
        action = "bid"
        reasons.append("you chose to draft anyway")

    if action == "bid":
        status = "running"
    elif action == "watch":
        status = "watch"
    else:
        status = "skipped" if user_settings(config).get("autonomy") == "auto_skip" else "recommended_skip"
    return {"decision": BidDecision(action=action, reasons=reasons).model_dump(), "status": status}
