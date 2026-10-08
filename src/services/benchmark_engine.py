"""Registry-driven relative financial benchmarking.

No benchmark is inferred or downloaded here. Every numeric value must carry a
source, and conflicts are surfaced instead of silently reconciled.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BenchmarkType(StrEnum):
    HISTORICAL = "HISTORICAL"
    PEER = "PEER"
    INDUSTRY = "INDUSTRY"


class Position(StrEnum):
    ABOVE = "ABOVE"
    BELOW = "BELOW"
    AVERAGE = "AVERAGE"
    UNKNOWN = "UNKNOWN"


class AvailableMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric: str = Field(min_length=1)
    value: Any
    source: str = Field(min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)
    year: int | None = None


class BenchmarkInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company: str = Field(min_length=1)
    metrics: list[AvailableMetric] = Field(default_factory=list)
    signals: list[dict[str, Any]] = Field(default_factory=list)


class BenchmarkItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric: str
    company_value: str
    benchmark_value: str
    benchmark_type: BenchmarkType
    position: Position
    interpretation: str
    confidence: str
    evidence_refs: list[str] = Field(default_factory=list)


class BenchmarkResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company: str
    benchmarks: list[BenchmarkItem] = Field(default_factory=list)
    relative_assessment: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class BenchmarkDefinition:
    metric: str
    company: str
    value: Any
    benchmark_type: BenchmarkType
    source: str
    evidence_refs: tuple[str, ...] = ()
    year: int | None = None


class BenchmarkRegistry:
    """Extensible, source-required benchmark registry."""

    def __init__(self) -> None:
        self._items: list[BenchmarkDefinition] = []

    def register_benchmark(
        self,
        metric: str,
        company: str,
        value: Any,
        benchmark_type: BenchmarkType | str,
        source: str | None = None,
        *,
        evidence_refs: list[str] | None = None,
        year: int | None = None,
    ) -> BenchmarkDefinition:
        if value is None or not str(source or "").strip():
            raise ValueError("Benchmark values require a source")
        definition = BenchmarkDefinition(
            metric=metric.strip().lower(), company=company.strip().upper(), value=value,
            benchmark_type=BenchmarkType(benchmark_type), source=source.strip(),
            evidence_refs=tuple(evidence_refs or ()), year=year,
        )
        self._items.append(definition)
        return definition

    def find(self, metric: str, company: str, benchmark_type: BenchmarkType) -> list[BenchmarkDefinition]:
        return [item for item in self._items if item.metric == metric.lower() and item.benchmark_type == benchmark_type and (
            benchmark_type != BenchmarkType.HISTORICAL or item.company == company.upper()
        )]


class BenchmarkResolver:
    def __init__(self, registry: BenchmarkRegistry | None = None) -> None:
        self.registry = registry or BenchmarkRegistry()

    def resolve(self, metric: str, company: str, benchmark_type: BenchmarkType) -> list[BenchmarkDefinition]:
        return self.registry.find(metric, company, benchmark_type)


class BenchmarkAnalyzer:
    """Compare available company metrics to registered benchmarks only."""

    def __init__(self, resolver: BenchmarkResolver | None = None) -> None:
        self.resolver = resolver or BenchmarkResolver()

    def analyze(self, payload: BenchmarkInput | dict[str, Any]) -> BenchmarkResult:
        request = payload if isinstance(payload, BenchmarkInput) else BenchmarkInput.model_validate(payload)
        metrics: dict[str, AvailableMetric] = {}
        limitations: list[str] = []
        for metric in request.metrics:
            if not metric.source.strip():
                limitations.append(f"Missing source for company metric {metric.metric}.")
                continue
            metrics.setdefault(metric.metric.lower(), metric)
        items: list[BenchmarkItem] = []
        assessments: list[str] = []
        for metric_name, company_metric in metrics.items():
            for benchmark_type in BenchmarkType:
                definitions = self.resolver.resolve(metric_name, request.company, benchmark_type)
                if not definitions:
                    continue
                if self._conflicting(definitions):
                    limitations.append(f"Conflicting {benchmark_type.value} benchmarks for {metric_name}; position is UNKNOWN.")
                    items.append(self._item(metric_name, company_metric, definitions[0], Position.UNKNOWN, "Benchmark conflict prevents a relative conclusion.", "LOW"))
                    continue
                for definition in definitions:
                    position = self._position(company_metric.value, definition.value)
                    refs = list(dict.fromkeys([*company_metric.evidence_refs, *definition.evidence_refs]))
                    if not refs:
                        limitations.append(f"No evidence reference for {metric_name} benchmark.")
                        position = Position.UNKNOWN
                    confidence = "HIGH" if refs and definition.source else "LOW"
                    items.append(self._item(metric_name, company_metric, definition, position, self._interpretation(metric_name, position, benchmark_type), confidence, refs))
                    if position != Position.UNKNOWN:
                        assessments.append(f"{metric_name} is {position.value.lower()} the {benchmark_type.value.lower()} benchmark.")
        for metric_name in metrics:
            if not any(item.metric == metric_name for item in items):
                limitations.append(f"No registered benchmark for {metric_name}; relative position is UNKNOWN.")
                items.append(BenchmarkItem(
                    metric=metric_name, company_value=str(metrics[metric_name].value), benchmark_value="",
                    benchmark_type=BenchmarkType.INDUSTRY, position=Position.UNKNOWN,
                    interpretation="Không có benchmark hợp lệ để so sánh.", confidence="LOW",
                    evidence_refs=list(metrics[metric_name].evidence_refs),
                ))
        if not request.metrics:
            limitations.append("No available financial metrics were supplied.")
        return BenchmarkResult(company=request.company.upper(), benchmarks=items, relative_assessment=assessments, limitations=list(dict.fromkeys(limitations)))

    @staticmethod
    def _conflicting(definitions: list[BenchmarkDefinition]) -> bool:
        values = [str(item.value) for item in definitions]
        return len(set(values)) > 1

    @staticmethod
    def _position(company_value: Any, benchmark_value: Any) -> Position:
        try:
            company = float(company_value)
            benchmark = float(benchmark_value)
        except (TypeError, ValueError):
            return Position.UNKNOWN
        if company > benchmark:
            return Position.ABOVE
        if company < benchmark:
            return Position.BELOW
        return Position.AVERAGE

    @staticmethod
    def _interpretation(metric: str, position: Position, benchmark_type: BenchmarkType) -> str:
        if position == Position.ABOVE:
            return f"{metric} cải thiện/tốt hơn benchmark {benchmark_type.value.lower()} theo evidence hiện có."
        if position == Position.BELOW:
            return f"{metric} thấp hơn benchmark {benchmark_type.value.lower()} theo evidence hiện có."
        if position == Position.AVERAGE:
            return f"{metric} ngang benchmark {benchmark_type.value.lower()} theo evidence hiện có."
        return "Chưa đủ evidence để xác định vị trí tương đối."

    @staticmethod
    def _item(metric: str, company_metric: AvailableMetric, definition: BenchmarkDefinition, position: Position, interpretation: str, confidence: str, refs: list[str] | None = None) -> BenchmarkItem:
        return BenchmarkItem(
            metric=metric, company_value=str(company_metric.value), benchmark_value=str(definition.value),
            benchmark_type=definition.benchmark_type, position=position, interpretation=interpretation,
            confidence=confidence, evidence_refs=list(dict.fromkeys(refs or [*company_metric.evidence_refs, *definition.evidence_refs])),
        )
