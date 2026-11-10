"""
conversation_graph.py - one thread per client conversation (requirement C1).

    START -> load_thread -> classify -> plan_reply -> draft_reply -> reply_compliance
          -> prepare_reply_approval -> reply_approval (interrupt) -> send -> END
                                         │edit -> prepare_reply_approval (shows the edit again)
                                         │reject -> END
thread_id = "conv:<user>:<marketplace thread id>"
"""

from langgraph.graph import END, START, StateGraph

from agent.nodes.base import guard, needs_attention
from agent.nodes.client_liaison import (
    after_reply_approval,
    classify,
    draft_reply,
    load_thread,
    plan_reply,
    prepare_reply_approval,
    reply_approval,
    reply_compliance,
    send,
)
from agent.state import ConvState


def build_conversation_graph() -> StateGraph:
    g = StateGraph(ConvState)
    for name, fn in [("load_thread", load_thread), ("classify", classify), ("plan_reply", plan_reply),
                     ("draft_reply", draft_reply), ("reply_compliance", reply_compliance),
                     ("prepare_reply_approval", prepare_reply_approval), ("reply_approval", reply_approval),
                     ("send", send), ("needs_attention", needs_attention)]:
        g.add_node(name, fn)
    g.add_edge(START, "load_thread")

    def chain(src, dst):
        g.add_conditional_edges(src, guard(dst), [dst, "needs_attention", END])

    chain("load_thread", "classify")
    chain("classify", "plan_reply")
    chain("plan_reply", "draft_reply")
    chain("draft_reply", "reply_compliance")
    chain("reply_compliance", "prepare_reply_approval")
    chain("prepare_reply_approval", "reply_approval")
    g.add_conditional_edges("reply_approval", after_reply_approval, ["send", "prepare_reply_approval", END])
    g.add_edge("send", END)
    g.add_edge("needs_attention", END)
    return g
