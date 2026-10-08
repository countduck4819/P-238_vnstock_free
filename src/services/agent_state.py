"""Typed state objects used by the bounded Financial Research Agent MVP."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, TypedDict

from src.services.agent_actions import PlannerAction

AgentStatus = Literal[
    "PLANNING", "EXECUTING", "NEEDS_CLARIFICATION", "COMPLETED", "FAILED"
]


@dataclass(frozen=True)
class ToolStep:
    query_type: str
    params: dict[str, Any]
    purpose: str = ""

    @property
    def key(self) -> str:
        return f"{self.query_type}:{sorted(self.params.items())}"


@dataclass
class Observation:
    tool: str
    status: str
    ticker: str | None = None
    tickers: list[str] = field(default_factory=list)
    metric: str | None = None
    year: int | None = None
    period: dict[str, Any] | None = None
    data: list[dict[str, Any]] = field(default_factory=list)
    source: str | None = None
    provenance: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_result(cls, result: dict[str, Any]) -> Observation:
        return cls(
            tool=str(result.get("tool", "execute_query")),
            status=str(result.get("status", "UNKNOWN")),
            ticker=result.get("ticker"),
            tickers=list(result.get("tickers") or []),
            metric=result.get("metric"),
            year=result.get("year"),
            period=result.get("period"),
            data=list(result.get("data") or []),
            source=result.get("source"),
            provenance=list(result.get("provenance") or []),
            errors=list(result.get("errors") or []),
            warnings=list(result.get("warnings") or []),
            raw=result,
        )


@dataclass
class AgentState:
    question: str
    goal: str = ""
    tickers: list[str] = field(default_factory=list)
    sector: str | None = None
    period: dict[str, Any] | None = None
    plan: list[ToolStep] = field(default_factory=list)
    current_step: int = 0
    completed_steps: list[str] = field(default_factory=list)
    observations: list[Observation] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    status: AgentStatus = "PLANNING"
    max_steps: int = 10

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LangGraphAgentState(TypedDict, total=False):
    """Typed state passed between meaningful LangGraph nodes."""

    question: str
    financial_blueprint: dict[str, Any] | None
    blueprint_used: bool
    evidence_plan: dict[str, Any] | None
    data_availability: dict[str, Any] | None
    external_recovery_evidence: list[dict[str, Any]]
    evidence_package: dict[str, Any] | None
    financial_analysis_result: dict[str, Any] | None
    financial_signals: dict[str, Any] | None
    benchmark_result: dict[str, Any] | None
    risk_review: dict[str, Any] | None
    analyst_report: dict[str, Any] | None
    goal: str
    analytical_concepts: list[str]
    tickers: list[str]
    sector: str | None
    period: dict[str, Any]
    plan: list[PlannerAction]
    pending_action: PlannerAction | None
    observations: list[Observation]
    tool_calls: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    normalized_evidence: list[dict[str, Any]]
    compact_observations: list[dict[str, Any]]
    warnings: list[str]
    missing_information: list[str]
    iteration_count: int
    max_iterations: int
    status: str
    decision: str
    final_answer: str
    results: list[dict[str, Any]]
    trace: list[dict[str, Any]]
    invalid_action_count: int
    llm_call_count: int
    tool_call_count: int
    replan_count: int
    max_llm_calls: int
    max_tool_calls: int
    max_replans: int
    synthesis_draft: Any
    synthesis_valid: bool
    external_research_required: bool
    web_queries: list[str]
    web_sources: list[dict[str, Any]]
    external_evidence: list[dict[str, Any]]
    source_conflicts: list[dict[str, Any]]
    claim_types: list[str]
    research_complete: bool
    web_call_count: int
    max_web_calls: int
