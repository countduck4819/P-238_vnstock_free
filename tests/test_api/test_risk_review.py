import pytest

from src.services.risk_review import RiskReviewEngine, RiskReviewResult


def _payload(signals=None, benchmarks=None, risks=None, score=80):
    return {
        "financial_analysis_result": {
            "executive_summary": [], "financial_trend": [], "profitability_analysis": [],
            "business_quality": [], "strengths": [],
            "risks": risks or [], "unknowns": [], "confidence_score": score,
        },
        "financial_signals": {
            "signals": signals or [], "overall_assessment": "x",
            "investment_relevance": "research only", "confidence": score,
        },
        "benchmark_result": {
            "company": "FPT", "benchmarks": benchmarks or [],
            "relative_assessment": [], "limitations": [],
        },
    }


def test_debt_growth_signal_creates_high_leverage_risk():
    result = RiskReviewEngine().review(_payload(signals=[{
        "name": "leverage_risk", "category": "LEVERAGE", "direction": "NEGATIVE",
        "strength": "HIGH", "explanation": "debt growth exceeds asset growth",
        "evidence_refs": ["fact:debt_growth:2024"],
    }]))
    assert result.overall_risk_level.value == "HIGH"
    assert result.risks[0].type.value == "LEVERAGE"
    assert result.risks[0].severity.value == "HIGH"
    assert result.risks[0].evidence_refs


def test_profit_up_cashflow_down_creates_earnings_quality_risk():
    result = RiskReviewEngine().review(_payload(signals=[
        {"name": "profit", "category": "PROFITABILITY", "direction": "POSITIVE", "strength": "MEDIUM", "explanation": "profit increased", "evidence_refs": ["profit"]},
        {"name": "cashflow", "category": "CASHFLOW", "direction": "NEGATIVE", "strength": "MEDIUM", "explanation": "cashflow decreased", "evidence_refs": ["cashflow"]},
    ]))
    assert any(item.type.value == "EARNINGS_QUALITY" for item in result.risks)


def test_industry_below_benchmark_creates_relative_weakness_risk():
    result = RiskReviewEngine().review(_payload(benchmarks=[{
        "metric": "roe", "company_value": "0.12", "benchmark_value": "0.18",
        "benchmark_type": "INDUSTRY", "position": "BELOW", "interpretation": "below",
        "confidence": "HIGH", "evidence_refs": ["industry:roe"],
    }]))
    assert result.risks[0].type.value == "FINANCIAL"
    assert result.risks[0].evidence_refs == ["industry:roe"]


def test_insufficient_data_is_unknown():
    result = RiskReviewEngine().review(_payload(score=20))
    assert result.overall_risk_level.value == "UNKNOWN"
    assert not result.risks
    assert result.unknown_risks
    assert result.confidence == 20


def test_risk_without_refs_is_rejected():
    with pytest.raises(Exception):
        RiskReviewResult.model_validate({
            "overall_risk_level": "HIGH",
            "risks": [{"type": "LEVERAGE", "severity": "HIGH", "direction": "NEGATIVE", "statement": "risk", "evidence_refs": [], "confidence": "HIGH"}],
            "risk_summary": "risk", "unknown_risks": [], "confidence": 80,
        })

