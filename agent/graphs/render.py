"""
render.py - draws both graphs FROM THE CODE (so the pictures can never be out of date).

Run:  python -m agent.graphs.render
Writes Mermaid diagrams to docs/images/bid_graph.mmd and conversation_graph.mmd
(GitHub renders Mermaid inside Markdown; docs/ARCHITECTURE.md embeds them).
"""

from agent.graphs.bid_graph import build_bid_graph
from agent.graphs.conversation_graph import build_conversation_graph
from agent.settings import ROOT

if __name__ == "__main__":
    out = ROOT / "docs" / "images"
    out.mkdir(parents=True, exist_ok=True)
    for name, builder in [("bid_graph", build_bid_graph), ("conversation_graph", build_conversation_graph)]:
        (out / f"{name}.mmd").write_text(builder().compile().get_graph().draw_mermaid(), encoding="utf-8")
        print(f"wrote docs/images/{name}.mmd")
