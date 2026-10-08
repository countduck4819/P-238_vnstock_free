"""Evidence Planning skill for the Financial Research Agent.

The planner is intentionally a pure mapping layer.  It consumes a validated
FinancialAnalysisBlueprint and produces an ordered collection plan; it does
not fetch evidence or calculate any metric.
"""
from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.services.financial_question_understanding import (
    EvidenceName,
    FinancialAnalysisBlueprint,
)

logger = logging.getLogger(__name__)


class EvidenceCategory(StrEnum):
    NUMERIC_FACT = "NUMERIC_FACT"
    DERIVED_METRIC = "DERIVED_METRIC"
    QUALITATIVE_KNOWLEDGE = "QUALITATIVE_KNOWLEDGE"
    EXTERNAL_EVENT = "EXTERNAL_EVENT"


Priority = Literal["HIGH", "MEDIUM", "LOW"]
Source = Literal["POSTGRES", "CALCULATION_ENGINE", "QDRANT", "WEB"]


class EvidencePlanItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: EvidenceName
    category: EvidenceCategory
    priority: Priority
    source_preference: list[Source] = Field(default_factory=list)
    fallback_source: list[Source] = Field(default_factory=list)
    required: bool = True


class EvidencePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    objective: str = Field(min_length=1, max_length=500)
    evidence_items: list[EvidencePlanItem] = Field(default_factory=list)


class EvidencePlanningSkill:
    """Map ontology evidence requirements to safe source preferences."""

    _NUMERIC: set[str] = {
        "revenue", "profit", "total_assets", "total_liabilities", "total_equity",
        "cash_flow", "valuation_multiple",
    }
    _DERIVED: set[str] = {
        "revenue_growth", "profit_growth", "net_margin", "roa", "roe",
    }
    _QUALITATIVE: set[str] = {"business_driver", "company_profile", "management", "industry_context"}
    _EXTERNAL: set[str] = {"current_events"}
    _HIGH: set[str] = {"revenue", "profit", "revenue_growth", "profit_growth", "current_events"}

    def plan(self, blueprint: FinancialAnalysisBlueprint | dict[str, Any]) -> EvidencePlan:
        validated = (
            blueprint
            if isinstance(blueprint, FinancialAnalysisBlueprint)
            else FinancialAnalysisBlueprint.model_validate(blueprint)
        )
        items: list[EvidencePlanItem] = []
        for requirement in validated.required_evidence:
            name = str(requirement.name)
            item = self._map_item(name, str(requirement.type))
            if not any(existing.name == item.name for existing in items):
                items.append(item)
        objective = self._objective(validated)
        result = EvidencePlan(objective=objective, evidence_items=items)
        logger.info(
            "Evidence plan created: intent=%s items=%d required=%d",
            validated.intent.value,
            len(items),
            sum(item.required for item in items),
        )
        return result

    def _map_item(self, name: str, evidence_type: str) -> EvidencePlanItem:
        # The blueprint ontology is authoritative; a mismatched type is not
        # silently repaired into a new metric.
        if name in self._NUMERIC and evidence_type == "NUMERIC":
            category = EvidenceCategory.NUMERIC_FACT
            preferred: list[Source] = ["POSTGRES"]
            fallback: list[Source] = []
        elif name in self._DERIVED and evidence_type == "DERIVED_METRIC":
            category = EvidenceCategory.DERIVED_METRIC
            preferred = ["CALCULATION_ENGINE"]
            fallback = ["POSTGRES"]
        elif name in self._QUALITATIVE and evidence_type == "QUALITATIVE":
            category = EvidenceCategory.QUALITATIVE_KNOWLEDGE
            preferred = ["QDRANT"]
            fallback = ["WEB"]
        elif name in self._EXTERNAL and evidence_type == "EXTERNAL":
            category = EvidenceCategory.EXTERNAL_EVENT
            preferred = ["WEB"]
            fallback = ["QDRANT"]
        else:
            raise ValueError(f"Evidence ontology/type mismatch: {name}/{evidence_type}")
        return EvidencePlanItem(
            name=name, category=category,
            priority="HIGH" if name in self._HIGH else "MEDIUM",
            source_preference=preferred, fallback_source=fallback, required=True,
        )

    @staticmethod
    def _objective(blueprint: FinancialAnalysisBlueprint) -> str:
        companies = ", ".join(blueprint.companies) or ", ".join(blueprint.sector) or "the requested scope"
        period = blueprint.period.start or blueprint.period.end
        suffix = f" for {period}" if period else ""
        return f"Collect evidence for {blueprint.intent.value} of {companies}{suffix}"

