"""Deterministic financial display formatting; no calculations of new metrics."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

RATIO_METRICS = {
    "net_revenue_yoy_growth", "net_profit_yoy_growth",
    "net_profit_margin", "roa", "roe",
}
MONETARY_METRICS = {
    "net_profit", "net_revenue", "profit_before_tax", "total_assets",
    "total_liabilities", "total_equity", "net_interest_income",
    "net_fee_and_commission_income", "provision_for_credit_losses",
}
MONETARY_UNITS = {"VND", "source_native_numeric"}
BILLION = Decimal("1000000000")


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _vietnamese_decimal(value: Decimal, places: int = 2) -> str:
    quantum = Decimal(1).scaleb(-places)
    rendered = f"{value.quantize(quantum, rounding=ROUND_HALF_UP):,.{places}f}"
    return rendered.replace(",", "_").replace(".", ",").replace("_", ".")


def format_financial_value(value: Any, metric: str, unit: str | None) -> dict:
    """Format an existing backend value without deriving or repairing it."""
    numeric = _decimal(value)
    if numeric is None:
        return {
            "raw_value": value, "formatted_value": None,
            "display_unit": unit, "status": "MISSING",
        }
    if metric in RATIO_METRICS or unit == "ratio":
        percentage = (numeric * Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return {
            "raw_value": value,
            "formatted_value": f"{percentage:.2f}%",
            "display_unit": "percent",
            "status": "OK",
        }
    if metric in MONETARY_METRICS and unit in MONETARY_UNITS:
        return {
            "raw_value": value,
            "formatted_value": f"{_vietnamese_decimal(numeric / BILLION)} tỷ đồng",
            "display_unit": "billion_vnd",
            "status": "OK",
        }
    return {
        "raw_value": value,
        "formatted_value": format(numeric, "f"),
        "display_unit": unit,
        "status": "OK",
    }
