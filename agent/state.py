"""
state.py - what each graph remembers WHILE it runs (requirement C2).

In simple words:
    The "state" is a shared notebook that every agent in the graph reads and
    writes. It only holds what THIS job (or THIS conversation) needs right now.

    Three things are kept apart on purpose:
      1. State            -> this file (current job: spec, risk, fit, draft, approval...)
      2. Execution trace  -> NOT here: every tool call goes to the MCP audit log and
                             LangSmith traces (tool name, arguments, result, trace id)
      3. Long-term memory -> NOT here: agent/memory/ (style + outcome stores), written
                             only through explicit promotion rules

    Reducers: Job Analyst, Risk Assessor and Fit Matcher run IN PARALLEL. Fields they
    all write (steps, usage) use a reducer (operator.add) so their updates are added
    together instead of overwriting each other.
"""

import operator
from typing import Annotated, Any, TypedDict


def latest(old, new):
    """Reducer for fields two parallel branches might both set (e.g. status on failure): last write wins."""
    return new


class BidState(TypedDict, total=False):
    user_id: str
    job: dict[str, Any]                 # the raw post from the marketplace (UNTRUSTED text inside)
    force_bid: bool                     # user clicked "draft anyway"
    job_spec: dict                      # JobSpec
    risk: dict                          # RiskReport
    fit: dict                           # FitReport
    decision: dict                      # BidDecision
    price: dict                         # PriceQuote
    evidence: list[dict]                # portfolio items the Writer was given
    draft_raw: dict                     # Writer's draft before claim verification
    draft: dict                         # ProposalDraft after verification / edits
    claims: dict                        # ClaimReport
    critiques: Annotated[list[dict], operator.add]   # every Critique, in order
    revisions: int                      # how many times the Critic sent it back
    compliance: dict                    # ComplianceVerdict
    marketplace_draft: dict             # draft id + dry-run preview (cost, balance)
    approval: dict                      # ApprovalDecision from the human
    submission: dict                    # proposal id, Connects spent
    status: Annotated[str, latest]      # running | skipped | recommended_skip | watch | awaiting_approval |
                                        # blocked | rejected | submitted | needs_attention | dead_letter
    error: Annotated[str, latest]
    steps: Annotated[int, operator.add]          # node runs so far (step budget)
    usage: Annotated[list[dict], operator.add]   # tokens + cost per LLM call (token budget)


class ConvState(TypedDict, total=False):
    user_id: str
    thread_id: str                      # the marketplace conversation id (= proposal id)
    messages: list[dict]                # the conversation (client text is UNTRUSTED)
    last_client_message: dict
    intent: dict                        # IntentOut + flags
    slots: list[dict]                   # interview slots offered
    reply: str
    compliance: dict
    approval: dict
    sent: dict
    status: str                         # running | nothing_to_do | awaiting_approval | sent | rejected | blocked | dead_letter
    error: str
    steps: Annotated[int, operator.add]
    usage: Annotated[list[dict], operator.add]
