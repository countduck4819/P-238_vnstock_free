"""Deterministic data-availability analysis for an Evidence Plan.

Availability here means *capability declared by the serving ontology*, not a
live row check.  The analyzer intentionally performs no I/O and never turns
missing data into zero.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.services.evidence_planning import (
    EvidenceCategory,
    EvidencePlan,
)

logger = logging.getLogger(__name__)


class AvailabilityItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence: str
    category: EvidenceCategory
    source: str


class MissingItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence: str
    reason: str


class DerivableItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric: str
    formula: str
    dependencies: list[str] = Field(default_factory=list)


class ExternalRequiredItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence: str
    source: str


class DataAvailabilityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    available: list[AvailabilityItem] = Field(default_factory=list)
    missing: list[MissingItem] = Field(default_factory=list)
    derivable: list[DerivableItem] = Field(default_factory=list)
    external_required: list[ExternalRequiredItem] = Field(default_factory=list)


@dataclass(frozen=True)
class MetricDefinition:
    """A metric's ontology definition, independent of any data value."""

    name: str
    formula: str | None = None
    dependencies: tuple[str, ...] = ()


class MetricRegistry:
    """Extensible registry of raw and derived financial metrics."""

    def __init__(self, definitions: list[MetricDefinition] | None = None) -> None:
        defaults = [
            MetricDefinition("net_revenue"),
            MetricDefinition("net_profit"),
            MetricDefinition("total_assets"),
            MetricDefinition("total_liabilities"),
            MetricDefinition("total_equity"),
            MetricDefinition("revenue_growth", "(current_revenue - prior_revenue) / prior_revenue", ("net_revenue",)),
            MetricDefinition("profit_growth", "(current_profit - prior_profit) / prior_profit", ("net_profit",)),
            MetricDefinition("net_margin", "net_profit / net_revenue", ("net_profit", "net_revenue")),
            MetricDefinition("roa", "net_income / average_total_assets", ("net_profit", "total_assets")),
            MetricDefinition("roe", "net_income / average_equity", ("net_profit", "total_equity")),
        ]
        self._definitions: dict[str, MetricDefinition] = {}
        for definition in [*(definitions or []), *defaults]:
            self.register(definition)

    def register(self, definition: MetricDefinition) -> None:
        if not definition.name or (definition.formula is None and definition.dependencies):
            raise ValueError("Invalid metric definition")
        self._definitions[definition.name] = definition

    def get(self, name: str) -> MetricDefinition | None:
        return self._definitions.get(name)

    def has_raw(self, name: str) -> bool:
        definition = self.get(name)
        return definition is not None and definition.formula is None


@dataclass(frozen=True)
class EvidenceDefinition:
    name: str
    category: EvidenceCategory
    source: str
    metric: str | None = None


class EvidenceRegistry:
    """Maps blueprint evidence names to source capabilities."""

    def __init__(self, definitions: list[EvidenceDefinition] | None = None) -> None:
        defaults = [
            EvidenceDefinition("revenue", EvidenceCategory.NUMERIC_FACT, "POSTGRES", "net_revenue"),
            EvidenceDefinition("profit", EvidenceCategory.NUMERIC_FACT, "POSTGRES", "net_profit"),
            EvidenceDefinition("total_assets", EvidenceCategory.NUMERIC_FACT, "POSTGRES", "total_assets"),
            EvidenceDefinition("total_liabilities", EvidenceCategory.NUMERIC_FACT, "POSTGRES", "total_liabilities"),
            EvidenceDefinition("total_equity", EvidenceCategory.NUMERIC_FACT, "POSTGRES", "total_equity"),
            EvidenceDefinition("cash_flow", EvidenceCategory.NUMERIC_FACT, "POSTGRES", "cash_flow"),
            EvidenceDefinition("valuation_multiple", EvidenceCategory.NUMERIC_FACT, "POSTGRES", "valuation_multiple"),
            EvidenceDefinition("revenue_growth", EvidenceCategory.DERIVED_METRIC, "CALCULATION_ENGINE", "revenue_growth"),
            EvidenceDefinition("profit_growth", EvidenceCategory.DERIVED_METRIC, "CALCULATION_ENGINE", "profit_growth"),
            EvidenceDefinition("net_margin", EvidenceCategory.DERIVED_METRIC, "CALCULATION_ENGINE", "net_margin"),
            EvidenceDefinition("roa", EvidenceCategory.DERIVED_METRIC, "CALCULATION_ENGINE", "roa"),
            EvidenceDefinition("roe", EvidenceCategory.DERIVED_METRIC, "CALCULATION_ENGINE", "roe"),
            EvidenceDefinition("business_driver", EvidenceCategory.QUALITATIVE_KNOWLEDGE, "QDRANT"),
            EvidenceDefinition("company_profile", EvidenceCategory.QUALITATIVE_KNOWLEDGE, "QDRANT"),
            EvidenceDefinition("management", EvidenceCategory.QUALITATIVE_KNOWLEDGE, "QDRANT"),
            EvidenceDefinition("industry_context", EvidenceCategory.QUALITATIVE_KNOWLEDGE, "QDRANT"),
            EvidenceDefinition("current_events", EvidenceCategory.EXTERNAL_EVENT, "WEB"),
        ]
        self._definitions: dict[str, EvidenceDefinition] = {}
        for definition in [*(definitions or []), *defaults]:
            self.register(definition)

    def register(self, definition: EvidenceDefinition) -> None:
        self._definitions[definition.name] = definition

    def get(self, name: str) -> EvidenceDefinition | None:
        return self._definitions.get(name)


class DataAvailabilityAnalyzer:
    """Resolve an Evidence Plan against static source and metric registries."""

    def __init__(
        self,
        metric_registry: MetricRegistry | None = None,
        evidence_registry: EvidenceRegistry | None = None,
    ) -> None:
        self.metrics = metric_registry or MetricRegistry()
        self.evidence = evidence_registry or EvidenceRegistry()

    def analyze(self, evidence_plan: EvidencePlan | dict[str, Any]) -> DataAvailabilityReport:
        plan = evidence_plan if isinstance(evidence_plan, EvidencePlan) else EvidencePlan.model_validate(evidence_plan)
        report = DataAvailabilityReport()
        for item in plan.evidence_items:
            definition = self.evidence.get(str(item.name))
            if definition is None:
                report.missing.append(MissingItem(evidence=str(item.name), reason="NOT_IN_EVIDENCE_REGISTRY"))
                continue
            if definition.category == EvidenceCategory.EXTERNAL_EVENT:
                report.external_required.append(
                    ExternalRequiredItem(evidence=definition.name, source=definition.source)
                )
                continue
            if definition.category == EvidenceCategory.QUALITATIVE_KNOWLEDGE:
                report.available.append(AvailabilityItem(
                    evidence=definition.name, category=definition.category, source=definition.source,
                ))
                continue
            if definition.category == EvidenceCategory.DERIVED_METRIC:
                metric = self.metrics.get(definition.metric or definition.name)
                if metric and metric.formula and all(self.metrics.has_raw(dep) for dep in metric.dependencies):
                    report.derivable.append(DerivableItem(
                        metric=definition.name, formula=metric.formula,
                        dependencies=list(metric.dependencies),
                    ))
                else:
                    report.missing.append(MissingItem(
                        evidence=definition.name, reason="DERIVATION_DEPENDENCY_UNAVAILABLE",
                    ))
                continue
            metric = self.metrics.get(definition.metric or definition.name)
            if metric and self.metrics.has_raw(metric.name):
                report.available.append(AvailabilityItem(
                    evidence=definition.name, category=definition.category, source=definition.source,
                ))
            else:
                report.missing.append(MissingItem(
                    evidence=definition.name, reason="SOURCE_CAPABILITY_UNAVAILABLE",
                ))
        logger.info(
            "Data availability analyzed: available=%d derivable=%d missing=%d external=%d",
            len(report.available), len(report.derivable), len(report.missing), len(report.external_required),
        )
        return report


class DataAvailabilityResolver(DataAvailabilityAnalyzer):
    """Compatibility-facing resolver service with an explicit ``resolve`` API."""

    def resolve(self, evidence_plan: EvidencePlan | dict[str, Any]) -> DataAvailabilityReport:
        return self.analyze(evidence_plan)
