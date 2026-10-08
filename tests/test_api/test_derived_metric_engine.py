import pytest

from src.services.derived_metrics import (
    DerivedMetricEngine,
    DerivedMetricError,
    MissingFactError,
    ZeroDenominatorError,
    calculate_metric,
)


@pytest.mark.parametrize(
    ("metric", "facts", "expected"),
    [
        ("revenue_growth", {"revenue_current": 120, "revenue_previous": 100}, 0.20),
        ("profit_growth", {"profit_current": 30, "profit_previous": 20}, 0.50),
        ("gross_margin", {"gross_profit": 40, "revenue": 100}, 0.40),
        ("operating_margin", {"operating_income": 25, "revenue": 100}, 0.25),
        ("net_margin", {"net_income": 12, "revenue": 100}, 0.12),
        ("ROA", {"net_income": 12, "total_assets": 100}, 0.12),
        ("ROE", {"net_income": 12_000, "equity": 50_000}, 0.24),
        ("debt_ratio", {"total_debt": 60, "total_assets": 100}, 0.60),
    ],
)
def test_all_supported_formulas(metric, facts, expected):
    result = calculate_metric(metric, facts)
    assert result["value"] == pytest.approx(expected)
    assert result["metric"] == metric.upper()
    assert result["confidence"] == "HIGH"
    assert result["formula"]


def test_aliases_are_supported():
    assert DerivedMetricEngine().calculate(
        "roe", {"net_profit": 10, "total_equity": 40}
    )["value"] == pytest.approx(0.25)
    assert DerivedMetricEngine().calculate(
        "debt_ratio", {"total_liabilities": 30, "assets": 100}
    )["value"] == pytest.approx(0.30)


def test_zero_denominator_is_rejected_not_zeroed():
    with pytest.raises(ZeroDenominatorError):
        calculate_metric("ROE", {"net_income": 12, "equity": 0})


def test_missing_fact_is_rejected():
    with pytest.raises(MissingFactError):
        calculate_metric("net_margin", {"net_income": 12})


def test_unknown_metric_is_rejected():
    with pytest.raises(DerivedMetricError):
        calculate_metric("invented_metric", {"a": 1, "b": 2})

