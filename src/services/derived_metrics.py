"""Deterministic, on-demand derived financial metrics."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

Facts = Mapping[tuple[str, int], Decimal | None]


class DerivedMetricError(ValueError):
    """Base error for invalid or unavailable derived-metric calculations."""


class MissingFactError(DerivedMetricError):
    pass


class ZeroDenominatorError(DerivedMetricError):
    pass


@dataclass(frozen=True)
class DerivedMetricDefinition:
    name: str
    formula: str
    inputs: tuple[tuple[str, ...], ...]


class MetricRegistry:
    """Closed, extensible ontology of metrics supported by the engine."""

    def __init__(self) -> None:
        self._definitions: dict[str, DerivedMetricDefinition] = {}
        for definition in (
            DerivedMetricDefinition("revenue_growth", "(revenue_current - revenue_previous) / revenue_previous", (("revenue_current", "net_revenue_current"), ("revenue_previous", "net_revenue_previous"))),
            DerivedMetricDefinition("profit_growth", "(profit_current - profit_previous) / profit_previous", (("profit_current", "net_income_current", "net_profit_current"), ("profit_previous", "net_income_previous", "net_profit_previous"))),
            DerivedMetricDefinition("gross_margin", "gross_profit / revenue", (("gross_profit",), ("revenue", "net_revenue"))),
            DerivedMetricDefinition("operating_margin", "operating_income / revenue", (("operating_income",), ("revenue", "net_revenue"))),
            DerivedMetricDefinition("net_margin", "net_income / revenue", (("net_income", "net_profit"), ("revenue", "net_revenue"))),
            DerivedMetricDefinition("roa", "net_income / total_assets", (("net_income", "net_profit"), ("total_assets", "assets"))),
            DerivedMetricDefinition("roe", "net_income / equity", (("net_income", "net_profit"), ("equity", "total_equity"))),
            DerivedMetricDefinition("debt_ratio", "total_debt / total_assets", (("total_debt", "total_liabilities", "debt"), ("total_assets", "assets"))),
        ):
            self.register(definition)

    def register(self, definition: DerivedMetricDefinition) -> None:
        key = definition.name.strip().lower()
        if not key or not definition.formula or not definition.inputs:
            raise ValueError("Invalid derived metric definition")
        self._definitions[key] = definition

    def get(self, metric: str) -> DerivedMetricDefinition | None:
        return self._definitions.get(str(metric).strip().lower())

    def names(self) -> tuple[str, ...]:
        return tuple(self._definitions)


METRIC_REGISTRY = MetricRegistry()


class DerivedMetricEngine:
    """Deterministic metric calculator; it never calls an LLM or persists data."""

    def __init__(self, registry: MetricRegistry | None = None) -> None:
        self.registry = registry or METRIC_REGISTRY

    def calculate(self, metric: str, facts: Mapping[str, Any]) -> dict[str, Any]:
        definition = self.registry.get(metric)
        if definition is None:
            raise DerivedMetricError(f"Unsupported derived metric: {metric}")
        normalized = {str(key).strip().lower(): value for key, value in facts.items()}
        values: list[Decimal] = []
        for aliases in definition.inputs:
            found = next((normalized[alias] for alias in aliases if alias in normalized), None)
            if found is None:
                raise MissingFactError(f"Missing input for {definition.name}: {aliases[0]}")
            try:
                values.append(Decimal(str(found)))
            except Exception as exc:
                raise DerivedMetricError(f"Non-numeric input for {definition.name}") from exc
        denominator = values[-1]
        if denominator == 0:
            raise ZeroDenominatorError(f"Zero denominator for {definition.name}")
        if definition.name in {"revenue_growth", "profit_growth"}:
            value = (values[0] - values[1]) / abs(values[1])
        else:
            value = values[0] / denominator
        return {
            "metric": definition.name.upper(),
            "value": float(value),
            "formula": definition.formula,
            "confidence": "HIGH",
        }


def calculate_metric(metric: str, facts: Mapping[str, Any]) -> dict[str, Any]:
    """Convenience API for the standalone ``metric + facts`` contract."""
    return DerivedMetricEngine().calculate(metric, facts)


def _result(ticker: str, year: int, code: str, value, status: str, inputs: list[dict]):
    return {
        "ticker": ticker,
        "year": year,
        "canonical_metric_code": code,
        "value": value,
        "metric_type": "DERIVED",
        "formula_version": "v1",
        "input_metrics": inputs,
        "calculation_status": status,
    }


def calculate(ticker: str, year: int, code: str, sector: str, facts: Facts):
    supported = {
        "net_revenue_yoy_growth": {"CORPORATE"},
        "net_profit_yoy_growth": {"CORPORATE", "BANK"},
        "net_profit_margin": {"CORPORATE"},
        "roa": {"CORPORATE", "BANK"},
        "roe": {"BANK"},
    }
    if code not in supported or sector not in supported[code]:
        return _result(ticker, year, code, None, "UNSUPPORTED", [])

    if code in {"net_revenue_yoy_growth", "net_profit_yoy_growth"}:
        base = "net_revenue" if code.startswith("net_revenue") else "net_profit"
        current = facts.get((base, year))
        previous = facts.get((base, year - 1))
        inputs = [
            {"metric": base, "year": year, "value": current},
            {"metric": base, "year": year - 1, "value": previous},
        ]
        if current is None or previous is None:
            return _result(ticker, year, code, None, "MISSING_INPUT", inputs)
        if previous == 0:
            return _result(ticker, year, code, None, "ZERO_DENOMINATOR", inputs)
        return _result(
            ticker,
            year,
            code,
            (current - previous) / abs(previous),
            "OK",
            inputs,
        )

    if code == "net_profit_margin":
        profit = facts.get(("net_profit", year))
        revenue = facts.get(("net_revenue", year))
        inputs = [
            {"metric": "net_profit", "year": year, "value": profit},
            {"metric": "net_revenue", "year": year, "value": revenue},
        ]
        if profit is None or revenue is None:
            return _result(ticker, year, code, None, "MISSING_INPUT", inputs)
        if revenue == 0:
            return _result(ticker, year, code, None, "ZERO_DENOMINATOR", inputs)
        return _result(ticker, year, code, profit / revenue, "OK", inputs)

    balance = "total_assets" if code == "roa" else "total_equity"
    profit = facts.get(("net_profit", year))
    current = facts.get((balance, year))
    previous = facts.get((balance, year - 1))
    inputs = [
        {"metric": "net_profit", "year": year, "value": profit},
        {"metric": balance, "year": year, "value": current},
        {"metric": balance, "year": year - 1, "value": previous},
    ]
    if profit is None or current is None or previous is None:
        return _result(ticker, year, code, None, "MISSING_INPUT", inputs)
    denominator = (current + previous) / Decimal(2)
    if denominator == 0:
        return _result(ticker, year, code, None, "ZERO_DENOMINATOR", inputs)
    return _result(ticker, year, code, profit / denominator, "OK", inputs)
