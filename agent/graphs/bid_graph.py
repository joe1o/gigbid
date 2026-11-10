"""
bid_graph.py - the hand-written LangGraph StateGraph for ONE job (requirement R3, C1).

                      ┌─> job_analyst ──┐
    START -> intake ──┼─> risk_assessor ┼─> decide ─(skip/watch)─> END
          (Send x3)   └─> fit_matcher ──┘     │ bid
                                              v
                    pricing -> writer -> verify_claims -> critic ─(revise, max 2)─> writer
                                                             │ ok
                                                             v
                       compliance ─(blocked)─> END
                             v
                       prepare_approval -> approval  (interrupt: the human decides)
                                             │approve      │edit               │reject
                                             v             v                   v
                                           submit    compliance_edit -> prepare_approval   END
                                             v
                                            END

Every edge goes through guard(): it stops on a final status and diverts to
needs_attention when the step or token budget is exceeded.
One thread per job: thread_id = "bid:<user>:<job_id>".
"""

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from agent.nodes.analyst import job_analyst
from agent.nodes.base import guard, needs_attention, node
from agent.nodes.compliance import compliance, compliance_edit
from agent.nodes.critic import after_critic, critic
from agent.nodes.decision import decide
from agent.nodes.fit_matcher import fit_matcher
from agent.nodes.pricing import pricing
from agent.nodes.risk_assessor import risk_assessor
from agent.nodes.submitter import after_approval, approval, prepare_approval, submit
from agent.nodes.verifier import verify_claims_node
from agent.nodes.writer import writer
from agent.state import BidState

PARALLEL = ["job_analyst", "risk_assessor", "fit_matcher"]


@node("intake")
async def intake(state, config):
    """The Scout hands a job in. Reset per-run fields so 'draft anyway' re-runs start clean."""
    return {"status": "running", "revisions": 0, "error": ""}


def fan_out(state) -> list[Send]:
    """Run the three analysis agents IN PARALLEL (LangGraph Send API)."""
    return [Send(name, state) for name in PARALLEL]


def build_bid_graph() -> StateGraph:
    g = StateGraph(BidState)
    for name, fn in [("intake", intake), ("job_analyst", job_analyst), ("risk_assessor", risk_assessor),
                     ("fit_matcher", fit_matcher), ("decide", decide), ("pricing", pricing), ("writer", writer),
                     ("verify_claims", verify_claims_node), ("critic", critic), ("compliance", compliance),
                     ("prepare_approval", prepare_approval), ("approval", approval),
                     ("compliance_edit", compliance_edit), ("submit", submit), ("needs_attention", needs_attention)]:
        g.add_node(name, fn)

    g.add_edge(START, "intake")
    g.add_conditional_edges("intake", fan_out, PARALLEL)
    for name in PARALLEL:                     # fan-in: decide waits for all three
        g.add_edge(name, "decide")

    def chain(src, dst):
        g.add_conditional_edges(src, guard(dst), [dst, "needs_attention", END])

    chain("decide", "pricing")
    chain("pricing", "writer")
    chain("writer", "verify_claims")
    chain("verify_claims", "critic")
    g.add_conditional_edges("critic", after_critic, ["writer", "compliance", "needs_attention", END])
    chain("compliance", "prepare_approval")
    chain("prepare_approval", "approval")
    g.add_conditional_edges("approval", after_approval, ["submit", "compliance_edit", END])
    chain("compliance_edit", "prepare_approval")
    g.add_edge("submit", END)
    g.add_edge("needs_attention", END)
    return g
