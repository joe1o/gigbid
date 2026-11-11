"""
Pricing Strategist - what to bid, and is the Connects cost worth it?

Rules (no LLM):
    start from the market median for this category,
    move to the 75th percentile when the fit is strong (>= 0.8),
    keep it inside the client's budget, never below the user's floor, round to $10.
    Connects are worth spending only if the balance covers the cost (incl. any extra cost
    from the platform policy).

Tools: marketplace market_stats, get_connects_balance, get_policy.
"""

from agent.handoffs import PriceQuote
from agent.nodes.base import node, tools, user_settings


@node("pricing")
async def pricing(state, config):
    job, fit = state["job"], state["fit"]
    t = tools(state, config)
    market = await t.call("pricing", "market_stats", {"category": job["category"]})
    balance = (await t.call("pricing", "get_connects_balance"))["balance"]
    policy = await t.call("pricing", "get_policy")
    floor = user_settings(config).get("fixed_floor_usd", 0)

    target = market["p75"] if fit["score"] >= 0.8 else market["median"]
    lo, hi = job["budget"]["min"], job["budget"]["max"]
    amount = max(min(max(target, lo), hi), floor)
    amount = round(amount / 10) * 10
    cost = job["connects_cost"] + policy.get("extra_connects_per_proposal", 0)
    worth = balance >= cost
    rationale = (f"Market {job['category']} median ${market['median']:.0f} (p25 ${market['p25']:.0f}, "
                 f"p75 ${market['p75']:.0f}); {'strong fit, so aiming at p75' if fit['score'] >= 0.8 else 'aiming at the median'}; "
                 f"kept inside the client's budget ${lo:.0f}-${hi:.0f} and above your floor ${floor:.0f}. "
                 f"Costs {cost} Connects of your {balance}.")
    quote = PriceQuote(amount=amount, rationale=rationale, market=market, connects_cost=cost,
                       connects_balance=balance, worth_connects=worth)
    out = {"price": quote.model_dump(), "policy": policy}     # later steps (Compliance) read the live policy
    if not worth:
        out.update(status="watch", error=f"not enough Connects: need {cost}, have {balance}")
    return out
