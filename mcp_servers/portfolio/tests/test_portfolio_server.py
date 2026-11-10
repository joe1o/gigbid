"""Portfolio MCP server tests through an in-memory MCP client."""

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from agent.mcp_client import GigBidMCP, ToolCallError
from mcp_servers.portfolio import server


def mcp_as() -> GigBidMCP:
    return GigBidMCP("ml_engineer", in_memory={"portfolio": server.mcp})


async def test_search_finds_skill_hidden_in_code():
    """'Celery' only appears in a code file, not in any README or CV."""
    hits = await mcp_as().call("fit_matcher", "search_evidence", {"requirement": "Celery background jobs", "k": 3})
    assert hits[0]["id"] == "ml-code-sentiment"
    assert {"type", "source", "date", "outcome"} <= set(hits[0])


async def test_search_with_filters():
    hits = await mcp_as().call("writer", "search_evidence",
                               {"requirement": "proposal", "k": 5, "filters": {"types": ["past_proposal"], "outcome": "won"}})
    assert hits and all(h["type"] == "past_proposal" and h["outcome"] == "won" for h in hits)


async def test_get_case_study_and_missing_id():
    item = await mcp_as().call("writer", "get_case_study", {"id": "ml-cs-churn"})
    assert item["project"] == "telecom-churn"
    with pytest.raises(ToolCallError):
        await mcp_as().call("writer", "get_case_study", {"id": "does-not-exist"})


async def test_list_skills():
    skills = await mcp_as().call("fit_matcher", "list_skills")
    assert any(s["skill"] == "Python" for s in skills)


async def test_resources_and_prompts():
    async with create_connected_server_and_client_session(server.mcp) as s:
        templates = [t.uriTemplate for t in (await s.list_resource_templates()).resourceTemplates]
        assert "portfolio://case/{id}" in templates and "portfolio://proposal/{id}" in templates
        case = await s.read_resource("portfolio://case/ml-cs-churn")
        assert "telecom" in case.contents[0].text
        prompts = [p.name for p in (await s.list_prompts()).prompts]
        assert "answer_screening_question" in prompts
