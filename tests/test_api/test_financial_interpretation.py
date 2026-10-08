import pytest

from src.services.financial_interpretation import FinancialInterpretationEngine, FinancialSignalResult


def _analysis(texts, confidence=80):
    return {
        "executive_summary": [], "financial_trend": texts, "profitability_analysis": [],
        "business_quality": [], "strengths": [], "risks": [], "unknowns": [],
        "confidence_score": confidence,
    }


def test_quality_growth_positive_signal_uses_refs():
    result = FinancialInterpretationEngine().interpret(_analysis([
        {"text": "Suy luận: Chất lượng tăng trưởng lợi nhuận có dấu hiệu cải thiện.", "type": "INFERENCE", "evidence_refs": ["fact:revenue_growth:2024", "fact:profit_growth:2024"], "confidence": "MEDIUM"},
    ]))
    signal = next(item for item in result.signals if item.name == "quality_growth")
    assert signal.direction.value == "POSITIVE"
    assert signal.evidence_refs
    assert result.confidence == 80


def test_missing_evidence_produces_unknown_signal_not_recommendation():
    result = FinancialInterpretationEngine().interpret(_analysis([
        {"text": "UNKNOWN: Chưa có đủ evidence chuỗi thời gian để phân tích xu hướng.", "type": "UNKNOWN", "evidence_refs": [], "confidence": "LOW"},
    ], confidence=30))
    assert any(item.direction.value == "UNKNOWN" for item in result.signals)
    assert "mua" not in result.investment_relevance.lower()
    assert "bán" not in result.investment_relevance.lower()


def test_non_unknown_signal_without_reference_is_rejected():
    with pytest.raises(Exception):
        FinancialSignalResult.model_validate({
            "signals": [{"name": "x", "category": "GROWTH", "direction": "POSITIVE", "strength": "HIGH", "explanation": "x", "evidence_refs": []}],
            "overall_assessment": "x", "investment_relevance": "x", "confidence": 80,
        })

