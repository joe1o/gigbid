"""
rnd_a_tools.py - R&D question A: does tool granularity change agent behaviour?

40 tasks with a known correct call (evals/datasets/tool_tasks.json), three tool menus:
    fine      : our real MCP tools (19 small tools, as shipped)
    coarse    : 3 big tools - marketplace / portfolio / workspace - each with an `action` field
    rewritten : the fine tools with descriptions rewritten to say WHEN to use them, with an example
For each task the model (gpt-oss-20b, the cheap-node model) must pick ONE tool call. We measure
tool-selection accuracy, argument accuracy (expected key arguments present and equal) and tokens.

    python -m evals.runners.rnd_a_tools    -> evals/results/rnd_a_tools.json
"""

import asyncio
import json

from evals.runners import harness

SERVERS = ("marketplace", "portfolio", "workspace")
BETTER = {   # rewritten descriptions: when to use + one example
    "search_jobs": "Use to FIND jobs by keyword and/or category (ml, web, data). Example: query='stripe', category='web'.",
    "get_job": "Use to READ one job post when you already know its id (job-NNN).",
    "get_client_history": "Use to judge if a CLIENT is trustworthy: spend, hires, rating, payment verified (client id cNN).",
    "get_connects_balance": "Use to check how many Connects (bid credits) the freelancer has left.",
    "get_policy": "Use to read the platform's current RULES and Connects costs.",
    "market_stats": "Use for typical PRICES of a job category (ml, web, data): p25, median, p75.",
    "list_proposals": "Use to see the status of proposals already SENT (viewed, replied, hired, lost).",
    "list_threads": "Use to see which CLIENTS replied and which conversations are unanswered.",
    "list_messages": "Use to READ the messages of one conversation (thread id = prop-...).",
    "create_proposal_draft": "Use to SAVE a proposal as a draft (never sends). Needs job_id, cover_letter, bid_amount, idempotency_key.",
    "submit_proposal": "Use ONLY after approval to SEND a saved draft (draft-...). dry_run=true previews without sending.",
    "send_message": "Use ONLY after approval to SEND a chat message to a client thread. dry_run=true previews.",
    "search_evidence": "Use to find PORTFOLIO PROOF for a skill or requirement. Example: requirement='stripe webhook', k=3.",
    "get_case_study": "Use to open ONE portfolio item in full by its id (e.g. ml-cs-churn).",
    "list_skills": "Use to list which skills the portfolio shows and how often.",
    "map_requirements": "Use to check SEVERAL requirements at once: which ones the portfolio can prove ('none' = no proof).",
    "get_free_slots": "Use to find FREE calendar times for an interview.",
    "create_interview_hold": "Use to put a TENTATIVE calendar hold on a chosen interview time.",
    "create_email_draft": "Use to SAVE an email draft (never sends). Needs subject, body, idempotency_key.",
}


async def fine_tools() -> list[dict]:
    from mcp.shared.memory import create_connected_server_and_client_session

    from mcp_servers.marketplace import server as m
    from mcp_servers.portfolio import server as p
    from mcp_servers.workspace import server as w

    out = []
    for name, srv in zip(SERVERS, (m, p, w)):
        async with create_connected_server_and_client_session(srv.mcp) as s:
            for t in (await s.list_tools()).tools:
                out.append({"server": name, "name": t.name, "description": t.description or "", "parameters": t.inputSchema})
    return out


def as_openai(tools: list[dict], descriptions: dict | None = None) -> list[dict]:
    return [{"type": "function", "function": {"name": t["name"], "description": (descriptions or {}).get(t["name"], t["description"]),
                                              "parameters": t["parameters"]}} for t in tools]


def coarse(tools: list[dict]) -> list[dict]:
    out = []
    for srv in SERVERS:
        mine = [t for t in tools if t["server"] == srv]
        listing = "; ".join(f"{t['name']}: {t['description'].split('.')[0]}" for t in mine)
        out.append({"type": "function", "function": {
            "name": srv, "description": f"All {srv} operations. Choose an action. Actions: {listing}.",
            "parameters": {"type": "object", "required": ["action", "params"], "properties": {
                "action": {"type": "string", "enum": [t["name"] for t in mine]},
                "params": {"type": "object", "description": "the arguments for the chosen action"}}}}})
    return out


def args_match(expected: dict, actual: dict) -> bool:
    for k, v in expected.items():
        a = actual.get(k)
        if isinstance(v, str):
            if not (isinstance(a, str) and v.lower() in a.lower()):
                return False
        elif isinstance(v, list):
            if not (isinstance(a, list) and {str(x).lower() for x in v} <= {str(x).lower() for x in a}):
                return False
        elif a != v and not (isinstance(v, int | float) and isinstance(a, int | float) and float(a) == float(v)):
            return False
    return True


async def evaluate(menu: str, tool_specs: list[dict], tasks: list[dict], server_of: dict) -> dict:
    from agent import llm

    model = llm._chat(llm.model_for("job_analyst")).bind_tools(tool_specs, tool_choice="required")
    rows = []
    for t in tasks:
        msg = await model.ainvoke("You are a freelancer's assistant. Make exactly ONE tool call for this request:\n" + t["task"])
        call = (msg.tool_calls or [{}])[0]
        name, args = call.get("name"), call.get("args", {}) or {}
        if menu == "coarse":
            right_tool = name == server_of[t["tool"]] and args.get("action") == t["tool"]
            args = args.get("params", {}) or {}
        else:
            right_tool = name == t["tool"]
        rows.append({"task": t["task"], "expected": t["tool"], "got": name if menu != "coarse" else f"{name}.{call.get('args', {}).get('action')}",
                     "tool_ok": right_tool, "args_ok": right_tool and args_match(t["args"], args),
                     "tokens": (msg.usage_metadata or {}).get("total_tokens", 0)})
    n = len(rows)
    return {"tool_selection_accuracy": round(sum(r["tool_ok"] for r in rows) / n, 3),
            "argument_accuracy": round(sum(r["args_ok"] for r in rows) / n, 3),
            "tokens_per_task": round(sum(r["tokens"] for r in rows) / n), "rows": rows}


async def main():
    tasks = json.loads((harness.ROOT / "evals/datasets/tool_tasks.json").read_text(encoding="utf-8"))
    tools = await fine_tools()
    server_of = {t["name"]: t["server"] for t in tools}
    menus = {"fine": as_openai(tools), "coarse": coarse(tools), "rewritten": as_openai(tools, BETTER)}
    results = {}
    for name, specs in menus.items():
        print(f"menu {name} ({len(specs)} tools) ...", flush=True)
        results[name] = await evaluate(name, specs, tasks, server_of)
        print({k: v for k, v in results[name].items() if k != "rows"}, flush=True)
    harness.save("rnd_a_tools", {"model": "openai/gpt-oss-20b", "n_tasks": len(tasks),
                                 "summary": {k: {kk: vv for kk, vv in v.items() if kk != "rows"} for k, v in results.items()},
                                 "results": results})


if __name__ == "__main__":
    harness.setup(fake_llm=False)
    asyncio.run(main())
