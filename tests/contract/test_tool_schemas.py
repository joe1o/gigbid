"""
Contract test (requirement A7): a "snapshot" of every MCP tool's signature.

In simple words:
    We save the exact shape of every tool (name, inputs, outputs, annotations) in
    tests/contract/snapshots/tools.json. If someone changes a tool by accident, the
    current shape no longer matches the saved one and CI fails.
    If the change is on purpose, regenerate the snapshot:
        UPDATE_SNAPSHOTS=1 pytest tests/contract
"""

import json
import os
from pathlib import Path

from mcp.shared.memory import create_connected_server_and_client_session

from mcp_servers.marketplace import server as marketplace
from mcp_servers.portfolio import server as portfolio
from mcp_servers.workspace import server as workspace

SNAPSHOT = Path(__file__).parent / "snapshots" / "tools.json"


async def current_tools() -> dict:
    out = {}
    for name, srv in [("marketplace", marketplace), ("portfolio", portfolio), ("workspace", workspace)]:
        async with create_connected_server_and_client_session(srv.mcp) as s:
            tools = (await s.list_tools()).tools
        out[name] = {t.name: {"input": t.inputSchema, "output": t.outputSchema,
                              "annotations": t.annotations.model_dump(exclude_none=True) if t.annotations else None}
                     for t in sorted(tools, key=lambda t: t.name)}
    return out


async def test_tool_signatures_match_snapshot():
    now = await current_tools()
    if os.getenv("UPDATE_SNAPSHOTS") == "1" or not SNAPSHOT.exists():
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(json.dumps(now, indent=2, sort_keys=True), encoding="utf-8")
    saved = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert now == saved, "An MCP tool signature changed. If intended, run: UPDATE_SNAPSHOTS=1 pytest tests/contract"


async def test_every_tool_has_annotations_and_output_schema():
    for server_tools in (await current_tools()).values():
        for name, t in server_tools.items():
            assert t["annotations"] and "readOnlyHint" in t["annotations"], name
            assert t["output"], f"{name} has no declared output schema"
