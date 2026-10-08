import pytest

from src.services.financial_reasoning import FinancialAnalysisResult, FinancialReasoningEngine


def test_full_package_produces_fact_and_inference_sections():
    result = FinancialReasoningEngine().analyze({
        "facts": [
            {"metric": "revenue_growth", "value": 0.10, "year": 2024, "source": "POSTGRESQL", "confidence": "HIGH"},
            {"metric": "profit_growth", "value": 0.20, "year": 2024, "source": "CALCULATION_ENGINE", "confidence": "MEDIUM"},
            {"metric": "net_margin", "value": 0.15, "year": 2024, "source": "CALCULATION_ENGINE", "confidence": "MEDIUM"},
        ],
        "interpretations": [{"text": "Có lợi thế công nghệ.", "source": "QDRANT", "confidence": "LOW"}],
        "confidence": "HIGH", "limitations": [], "conflict": False, "conflicts": [],
    })
    assert result.executive_summary[0].type.value == "INFERENCE"
    assert any(item.type.value == "FACT" for item in result.financial_trend)
    assert any(item.type.value == "INFERENCE" for item in result.financial_trend)
    assert result.business_quality[0].type.value == "FACT"
    assert result.confidence_score == 100
    assert all(item.evidence_refs for section in (result.executive_summary, result.financial_trend, result.business_quality) for item in section if item.type.value != "UNKNOWN")


def test_missing_cashflow_becomes_unknown():
    result = FinancialReasoningEngine().analyze({
        "facts": [{"metric": "revenue", "value": 100, "year": 2024, "source": "POSTGRESQL", "confidence": "HIGH"}],
        "interpretations": [], "confidence": "HIGH",
        "limitations": ["Cashflow evidence missing"], "conflict": False, "conflicts": [],
    })
    assert any(item.type.value == "UNKNOWN" and "Cashflow" in item.text for item in result.unknowns)
    assert result.confidence_score < 100


def test_conflict_generates_referenced_risk():
    result = FinancialReasoningEngine().analyze({
        "facts": [{"metric": "ROE", "value": 0.24, "year": 2024, "source": "POSTGRESQL", "confidence": "HIGH"}],
        "interpretations": [], "confidence": "LOW", "limitations": [], "conflict": True,
        "conflicts": [{"key": "roe:2024", "selected_source": "POSTGRESQL", "candidates": []}],
    })
    assert result.risks[0].type.value == "RISK"
    assert result.risks[0].evidence_refs == ["conflict:roe:2024"]


def test_empty_package_does_not_hallucinate():
    result = FinancialReasoningEngine().analyze({
        "facts": [], "interpretations": [], "confidence": "LOW", "limitations": [],
        "conflict": False, "conflicts": [],
    })
    assert result.executive_summary[0].type.value == "UNKNOWN"
    assert result.confidence_score == 0
    assert all(item.type.value == "UNKNOWN" for item in result.executive_summary)


def test_fact_without_reference_is_rejected_by_schema():
    with pytest.raises(Exception):
        FinancialAnalysisResult.model_validate({
            "executive_summary": [{"text": "Có số liệu", "type": "FACT", "evidence_refs": [], "confidence": "HIGH"}],
            "financial_trend": [], "profitability_analysis": [], "business_quality": [],
            "strengths": [], "risks": [], "unknowns": [], "confidence_score": 80,
        })
