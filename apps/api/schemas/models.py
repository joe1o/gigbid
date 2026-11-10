"""
models.py - the typed API contract (request + response shapes).

FastAPI turns these into an OpenAPI schema; the React app's TypeScript types are
GENERATED from that schema (apps/web/src/lib/api/schema.d.ts), so frontend and backend
can never silently disagree about a field.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

Autonomy = Literal["manual", "auto_skip"]


class Search(BaseModel):
    query: str = ""
    category: Literal["ml", "web", "data"] | None = None


class Settings(BaseModel):
    persona: str                       # whose portfolio (a preset persona or the user's own copy)
    account: str                       # which GigSim account is connected
    name: str
    headline: str = ""
    fixed_floor_usd: float = Field(ge=0)
    hourly_floor_usd: float = Field(ge=0)
    autonomy: Autonomy = "manual"
    connects_weekly_budget: int = Field(ge=0, le=500)
    searches: list[Search] = Field(default_factory=list)


class SignupIn(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8, max_length=200)


class LoginIn(BaseModel):
    email: str
    password: str


class Account(BaseModel):
    account: str
    connected_at: float


class UserOut(BaseModel):
    user_id: str
    email: str
    onboarded: bool
    settings: Settings | None = None
    gigsim: Account | None = None
    upwork_connected: bool = False


class OnboardIn(BaseModel):
    persona: Literal["ml_engineer", "web_developer", "data_analyst"]
    own_profile: bool = False          # true = start a private, editable copy of the portfolio
    account: Literal["ml_engineer", "web_developer", "data_analyst"]
    fixed_floor_usd: float = Field(ge=0)
    hourly_floor_usd: float = Field(ge=0)
    connects_weekly_budget: int = Field(ge=0, le=500)
    autonomy: Autonomy = "manual"
    searches: list[Search] = Field(default_factory=list)


class SettingsIn(BaseModel):
    fixed_floor_usd: float = Field(ge=0)
    hourly_floor_usd: float = Field(ge=0)
    connects_weekly_budget: int = Field(ge=0, le=500)
    autonomy: Autonomy
    searches: list[Search]


class PortfolioItemIn(BaseModel):
    type: Literal["cv", "case_study", "repo_readme", "code", "review", "past_proposal"]
    title: str = Field(min_length=3, max_length=200)
    project: str | None = None
    skills: list[str] = Field(default_factory=list, max_length=20)
    text: str = Field(min_length=20, max_length=8000)
    outcome: Literal["won", "replied", "ignored"] | None = None


class PortfolioOut(BaseModel):
    persona: str
    name: str
    headline: str
    editable: bool
    items: list[dict[str, Any]]


class JobSummary(BaseModel):
    job_id: str
    thread_id: str
    title: str
    category: str
    budget_min: float
    budget_max: float
    connects_cost: int
    posted_at: str | None = None
    status: str = Field(description="analysing | awaiting_approval | recommended_skip | skipped | watch | "
                                    "submitted | rejected | blocked | queued | needs_attention | dead_letter | error")
    fit: float | None = None
    risk_level: str | None = None
    risk_flags: list[str] = Field(default_factory=list)
    action: str | None = None
    reasons: list[str] = Field(default_factory=list)
    price: float | None = None
    proposal_id: str | None = None
    tokens: int = 0
    cost_usd: float = 0.0
    agent_seconds: float = 0.0
    rejection_reason: str | None = None
    error: str | None = None
    updated_at: float = 0.0


class JobDetail(BaseModel):
    summary: JobSummary
    job: dict[str, Any]
    state: dict[str, Any]
    approval: dict[str, Any] | None = Field(None, description="the pending approval payload (interrupt), if any")
    next: list[str] = Field(default_factory=list)


class DecisionIn(BaseModel):
    action: Literal["approve", "edit", "reject"]
    cover_letter: str | None = Field(None, max_length=6000)
    screening_answers: list[str] | None = None
    reason: str | None = Field(None, max_length=500)


class RegenerateIn(BaseModel):
    paragraph_index: int = Field(ge=0, le=20)
    instruction: str = Field("", max_length=300)


class RegenerateOut(BaseModel):
    paragraph: str
    claims: list[dict[str, Any]]


class HistoryItem(BaseModel):
    checkpoint_id: str
    next: list[str]
    status: str | None = None
    step: int | None = None


class Started(BaseModel):
    thread_id: str
    status: str


class ScoutOut(BaseModel):
    new_jobs: int
    duplicates: int


class PipelineCard(BaseModel):
    job_id: str
    title: str
    category: str
    status: str
    proposal_id: str | None = None
    bid_amount: float | None = None
    connects_spent: int | None = None


class PipelineOut(BaseModel):
    columns: dict[str, list[PipelineCard]]


class LastMessage(BaseModel):
    sender: str
    text: str


class ThreadSummary(BaseModel):
    thread_id: str
    job_id: str
    job_title: str
    status: str
    last_message: LastMessage
    unanswered: bool
    draft_status: str | None = None


class ThreadDetail(BaseModel):
    thread_id: str
    job_title: str
    messages: list[dict[str, Any]]
    status: str | None = None
    approval: dict[str, Any] | None = None


class CategoryStats(BaseModel):
    category: str
    sent: int
    replied: int
    hired: int
    reply_rate: float
    hire_rate: float


class CountRow(BaseModel):
    label: str
    count: float


class Analytics(BaseModel):
    by_category: list[CategoryStats]
    connects_by_outcome: list[CountRow]
    proposals_analysed: int
    avg_cost_usd_per_job: float
    avg_cost_usd_per_proposal: float
    p50_seconds_per_job: float
    p95_seconds_per_job: float
    rejection_reasons: list[CountRow]
    skip_reasons: list[CountRow]


class MemoryItem(BaseModel):
    namespace: str
    key: str
    rule: str | None = None
    value: dict[str, Any]


class Health(BaseModel):
    marketplace: Literal["ok", "down"]
    detail: str = ""
    queued_jobs: int = 0
