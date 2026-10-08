"""Schema-validated actions and deterministic validation for the agent graph."""
from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.services.query_tools import (
    BASE_METRICS,
    DERIVED_METRICS,
    DOCUMENT_TYPES,
    ticker_taxonomy,
)

ApprovedAction = Literal[
    "FACT", "TIME_SERIES", "COMPARE", "RANK", "EVALUATION", "COMPANY_KNOWLEDGE",
    "WEB_SEARCH",
]

# Single source of truth for the action -> QueryHarness tool mapping.  Keeping
# this registry next to the validated action schema prevents EvidencePlan and
# the executor from drifting apart.
TOOL_REGISTRY: dict[str, str] = {
    "FACT": "get_fact",
    "TIME_SERIES": "get_timeseries",
    "COMPARE": "compare",
    "RANK": "rank",
    "EVALUATION": "evaluate_stock",
    "COMPANY_KNOWLEDGE": "search_company_knowledge",
    "WEB_SEARCH": "web_search",
}


def registered_tool(action: str) -> str | None:
    """Return the registered implementation name for an action."""
    return TOOL_REGISTRY.get(str(action or "").strip().upper())


class PlannerAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: ApprovedAction
    ticker: str | None = None
    tickers: list[str] = Field(default_factory=list)
    metric: str | None = None
    year: int | None = None
    start_year: int | None = None
    end_year: int | None = None
    sector: str | None = None
    limit: int = 5
    descending: bool = True
    document_types: list[str] = Field(default_factory=list)
    query_text: str | None = None
    top_k: int = 3
    web_query: str | None = None
    max_results: int = 5
    recency_days: int | None = 365
    reason: str = ""

    @property
    def key(self) -> str:
        return json.dumps(
            {"action": self.action, "params": self.to_params()},
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )

    def to_params(self) -> dict[str, Any]:
        if self.action == "FACT":
            return {"ticker": self.ticker, "metric": self.metric, "year": self.year}
        if self.action == "TIME_SERIES":
            return {
                "ticker": self.ticker, "metric": self.metric,
                "start_year": self.start_year, "end_year": self.end_year,
            }
        if self.action == "COMPARE":
            return {"tickers": self.tickers, "metric": self.metric, "year": self.year}
        if self.action == "RANK":
            return {
                "metric": self.metric, "year": self.year, "sector": self.sector,
                "limit": self.limit, "descending": self.descending,
            }
        if self.action == "EVALUATION":
            return {"ticker": self.ticker, "year": self.year}
        if self.action == "WEB_SEARCH":
            return {
                "query": self.web_query or "", "max_results": self.max_results,
                "recency_days": self.recency_days,
            }
        return {
            "ticker": self.ticker,
            "query": self.query_text or "",
            "document_types": self.document_types or ["company_profile"],
            "top_k": self.top_k,
        }


class PlannerOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str
    actions: list[PlannerAction] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)


class NextDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["CONTINUE", "REPLAN", "COMPLETE", "CLARIFY"]
    reason: str = ""
    actions: list[PlannerAction] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)


class ActionValidator:
    """Reject invented or unsupported actions before QueryHarness execution."""

    def validate(
        self, action: PlannerAction, executed_keys: set[str], *,
        allowed_tickers: set[str] | None = None,
        requested_years: set[int] | None = None,
        observed_years: set[int] | None = None,
    ) -> tuple[bool, str | None]:
        if action.key in executed_keys:
            return False, "DUPLICATE_ACTION"
        taxonomy = ticker_taxonomy()
        ticker = (action.ticker or "").upper()
        sector = (action.sector or taxonomy.get(ticker) or "").upper()
        all_metrics = set().union(*BASE_METRICS.values(), DERIVED_METRICS)

        if action.action in {"FACT", "TIME_SERIES", "EVALUATION", "COMPANY_KNOWLEDGE"}:
            if not ticker or ticker not in taxonomy:
                return False, "INVALID_OR_MISSING_TICKER"
            if allowed_tickers and ticker not in allowed_tickers:
                return False, "TICKER_NOT_GROUNDED_IN_REQUEST"
            action.ticker = ticker
        if action.action == "COMPARE":
            action.tickers = [str(value).upper() for value in action.tickers]
            if len(action.tickers) < 2 or any(value not in taxonomy for value in action.tickers):
                return False, "INVALID_OR_MISSING_TICKERS"
            if allowed_tickers and any(value not in allowed_tickers for value in action.tickers):
                return False, "TICKER_NOT_GROUNDED_IN_REQUEST"
        if action.action == "RANK" and sector not in BASE_METRICS:
            return False, "INVALID_OR_MISSING_SECTOR"
        if action.action == "RANK":
            action.sector = sector
        if action.action in {"FACT", "TIME_SERIES", "COMPARE", "RANK"}:
            if action.metric not in all_metrics:
                return False, "INVALID_METRIC"
            applicable_sectors = DERIVED_METRICS.get(action.metric)
            if applicable_sectors and sector and sector not in applicable_sectors:
                return False, "METRIC_NOT_APPLICABLE"
            if action.metric in BASE_METRICS.get("CORPORATE", set()) | BASE_METRICS.get("BANK", set()):
                if sector and action.metric not in BASE_METRICS.get(sector, set()):
                    return False, "METRIC_NOT_APPLICABLE"
            if action.action == "COMPARE":
                compared_sectors = {taxonomy[value] for value in action.tickers}
                if applicable_sectors and not compared_sectors.issubset(applicable_sectors):
                    return False, "METRIC_NOT_APPLICABLE"
                if any(
                    action.metric not in BASE_METRICS.get(value, set())
                    for value in compared_sectors
                ) and action.metric not in DERIVED_METRICS:
                    return False, "METRIC_NOT_APPLICABLE"
        if action.action in {"FACT", "COMPARE", "RANK"} and not self._valid_year(action.year):
            return False, "INVALID_OR_MISSING_YEAR"
        if action.action == "TIME_SERIES":
            if not self._valid_year(action.start_year) or not self._valid_year(action.end_year):
                return False, "INVALID_PERIOD"
            if int(action.start_year) > int(action.end_year):
                return False, "INVALID_PERIOD"
        action_years = {
            value for value in (action.year, action.end_year)
            if isinstance(value, int)
        }
        grounded_years = set(requested_years or set()) | set(observed_years or set())
        if action_years and grounded_years and not action_years.issubset(grounded_years):
            return False, "YEAR_NOT_GROUNDED_IN_REQUEST_OR_OBSERVATION"
        if action_years and not grounded_years and action.action != "EVALUATION":
            return False, "YEAR_NOT_GROUNDED_IN_REQUEST_OR_OBSERVATION"
        if action.action == "EVALUATION" and action.year is not None:
            if not self._valid_year(action.year):
                return False, "INVALID_YEAR"
            if requested_years and action.year not in requested_years:
                return False, "YEAR_NOT_GROUNDED_IN_REQUEST_OR_OBSERVATION"
        if action.action == "RANK" and not 1 <= action.limit <= 100:
            return False, "INVALID_LIMIT"
        if action.action == "COMPANY_KNOWLEDGE":
            if any(value not in DOCUMENT_TYPES for value in action.document_types):
                return False, "INVALID_DOCUMENT_TYPE"
            if not 1 <= action.top_k <= 20:
                return False, "INVALID_TOP_K"
        if action.action == "WEB_SEARCH":
            query = str(action.web_query or "").strip()
            if not 3 <= len(query) <= 300:
                return False, "INVALID_WEB_QUERY"
            if not 1 <= action.max_results <= 10:
                return False, "INVALID_WEB_RESULT_LIMIT"
            if action.recency_days is not None and not 1 <= action.recency_days <= 3650:
                return False, "INVALID_WEB_RECENCY"
        return True, None

    @staticmethod
    def _valid_year(value: Any) -> bool:
        return isinstance(value, int) and 1900 <= value <= 2100
