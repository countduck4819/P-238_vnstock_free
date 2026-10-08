"""Deterministic fusion of heterogeneous financial evidence.

Numerical values are never repaired by an LLM. Conflicting candidates are
retained in conflict metadata instead of being silently discarded.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FusedFact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticker: str | None = None
    metric: str
    value: Any
    year: int | None = None
    source: str
    confidence: str
    provenance: dict[str, Any] = Field(default_factory=dict)


class FusedInterpretation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticker: str | None = None
    text: str
    source: str
    confidence: str
    provenance: dict[str, Any] = Field(default_factory=dict)


class EvidenceConflict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    selected_source: str
    candidates: list[dict[str, Any]] = Field(default_factory=list)


class EvidencePackage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    facts: list[FusedFact] = Field(default_factory=list)
    interpretations: list[FusedInterpretation] = Field(default_factory=list)
    confidence: str = "LOW"
    limitations: list[str] = Field(default_factory=list)
    conflict: bool = False
    conflicts: list[EvidenceConflict] = Field(default_factory=list)
    external_candidates: list[dict[str, Any]] = Field(default_factory=list)


SOURCE_PRIORITY = {
    "POSTGRES": 1,
    "POSTGRESQL": 1,
    "POSTGRESQL_DERIVED": 2,
    "CALCULATION_ENGINE": 2,
    "DERIVED": 2,
    "TIER_1": 3,
    "TIER_2": 3,
    "TIER_3": 3,
    "WEB": 3,
    "EXTERNAL": 3,
    "QDRANT": 4,
}


def _source(item: dict[str, Any], default: str) -> str:
    raw_source = str(item.get("source_type") or item.get("source") or default)
    if raw_source.lower().startswith(("http://", "https://")):
        return "EXTERNAL"
    value = raw_source.upper()
    if value in {"TIER_1", "TIER_2", "TIER_3"}:
        return value
    if value in {"POSTGRESQL_DERIVED", "CALCULATION_ENGINE", "DERIVED"}:
        return value
    if "QDRANT" in value:
        return "QDRANT"
    if "POSTGRES" in value:
        return "POSTGRESQL"
    if value in {"WEB", "EXTERNAL"}:
        return "EXTERNAL"
    return value


def _numeric_equal(left: Any, right: Any) -> bool:
    try:
        return Decimal(str(left)) == Decimal(str(right))
    except (InvalidOperation, ValueError):
        return str(left).strip() == str(right).strip()


class EvidenceFusionNode:
    """Fuse evidence while preserving provenance and disagreement metadata."""

    def fuse(
        self,
        postgres_evidence: list[dict[str, Any]] | None = None,
        derived_metrics: list[dict[str, Any]] | None = None,
        qdrant_evidence: list[dict[str, Any]] | None = None,
        external_evidence: list[dict[str, Any]] | None = None,
    ) -> EvidencePackage:
        candidates: list[dict[str, Any]] = []
        for item in postgres_evidence or []:
            self._add_numeric(candidates, item, "POSTGRESQL")
        for item in derived_metrics or []:
            self._add_numeric(candidates, item, "CALCULATION_ENGINE")
        external_candidates: list[dict[str, Any]] = []
        for item in external_evidence or []:
            if (
                item.get("numerical_truth") is False
                or (item.get("metadata") or {}).get("numerical_truth") is False
            ):
                external_candidates.append(dict(item))
                continue
            self._add_numeric(candidates, item, "EXTERNAL")
        interpretations: list[FusedInterpretation] = []
        for item in qdrant_evidence or []:
            text = str(item.get("text") or item.get("summary") or item.get("content") or "").strip()
            if text:
                interpretations.append(FusedInterpretation(
                    text=text, source="QDRANT", confidence="LOW",
                    ticker=item.get("ticker"),
                    provenance={key: item[key] for key in ("source_id", "url", "title") if item.get(key)},
                ))
        grouped: dict[str, list[dict[str, Any]]] = {}
        for candidate in candidates:
            grouped.setdefault(candidate["key"], []).append(candidate)
        facts: list[FusedFact] = []
        conflicts: list[EvidenceConflict] = []
        for key, values in grouped.items():
            values.sort(key=lambda item: SOURCE_PRIORITY.get(item["source"], 99))
            selected = values[0]
            facts.append(FusedFact(
                ticker=selected.get("ticker"), metric=selected["metric"], value=selected["value"], year=selected["year"],
                source=selected["source"], confidence=selected["confidence"],
                provenance=selected["provenance"],
            ))
            if any(not _numeric_equal(selected["value"], item["value"]) for item in values[1:]):
                conflicts.append(EvidenceConflict(
                    key=key, selected_source=selected["source"],
                    candidates=[{
                        "source": item["source"], "value": item["value"],
                        "year": item["year"], "provenance": item["provenance"],
                    } for item in values],
                ))
        limitations = [
            f"Evidence conflict detected for {conflict.key}; values were not silently reconciled."
            for conflict in conflicts
        ]
        if not facts and not interpretations:
            limitations.append("No evidence was available for fusion.")
        confidence = self._confidence(facts, interpretations, conflicts)
        return EvidencePackage(
            facts=facts, interpretations=interpretations, confidence=confidence,
            limitations=limitations, conflict=bool(conflicts), conflicts=conflicts,
            external_candidates=external_candidates,
        )

    @staticmethod
    def _add_numeric(candidates: list[dict[str, Any]], item: dict[str, Any], default: str) -> None:
        value = item.get("value")
        metric = str(item.get("metric") or item.get("canonical_metric_code") or "").strip()
        if value is None or not metric:
            return
        source = _source(item, default)
        year = item.get("year")
        ticker = item.get("ticker")
        candidates.append({
            "key": f"{str(ticker).upper() + ':' if ticker else ''}{metric.lower()}:{year or ''}",
            "ticker": str(ticker).upper() if ticker else None,
            "metric": metric, "value": value,
            "year": year if isinstance(year, int) else None, "source": source,
            "confidence": "HIGH" if source == "POSTGRESQL" else "MEDIUM" if source in {"CALCULATION_ENGINE", "POSTGRESQL_DERIVED"} else "LOW",
            "provenance": {
                key: item[key]
                for key in ("source_id", "source", "url", "title", "formula", "retrieved_date")
                if item.get(key)
            },
        })

    @staticmethod
    def _confidence(
        facts: list[FusedFact], interpretations: list[FusedInterpretation], conflicts: list[EvidenceConflict],
    ) -> str:
        if conflicts:
            return "LOW"
        if any(fact.source == "POSTGRESQL" for fact in facts):
            return "HIGH"
        if facts or interpretations:
            return "MEDIUM"
        return "LOW"
