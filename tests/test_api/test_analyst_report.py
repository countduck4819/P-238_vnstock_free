import pytest

from src.services.analyst_report import AnalystReport, AnalystReportGenerator


def payload(score=90, risks=None, unknowns=None):
    return {
        "financial_analysis_result": {
            "executive_summary": [], "financial_trend": [], "profitability_analysis": [],
            "business_quality": [], "strengths": [{"text": "Có bằng chứng hoạt động ổn định.", "type": "FACT", "evidence_refs": ["fact:1"], "confidence": "HIGH"}],
            "risks": [], "unknowns": unknowns or [], "confidence_score": score,
        },
        "financial_signals": {
            "signals": [{"name": "growth", "category": "GROWTH", "direction": "POSITIVE", "strength": "HIGH", "explanation": "Tăng trưởng tích cực.", "evidence_refs": ["fact:growth"]}],
            "overall_assessment": "x", "investment_relevance": "research only", "confidence": score,
        },
        "benchmark_result": {"company": "FPT", "benchmarks": [], "relative_assessment": [], "limitations": []},
        "risk_review": {"overall_risk_level": "HIGH" if risks else "UNKNOWN", "risks": risks or [], "risk_summary": "x", "unknown_risks": [], "confidence": score},
    }


def test_full_evidence_produces_complete_traceable_report():
    report = AnalystReportGenerator().generate(payload())
    assert report.title == "Analyst Report - FPT"
    assert report.evidence_coverage == "COMPLETE"
    assert "FACT:" in report.financial_assessment or report.strengths
    assert any("INTERPRETATION:" in item for item in report.strengths)


def test_missing_data_is_explicitly_reported():
    report = AnalystReportGenerator().generate(payload(score=40, unknowns=[{"text": "Cashflow missing", "type": "UNKNOWN", "evidence_refs": [], "confidence": "LOW"}]))
    assert report.evidence_coverage == "LIMITED"
    assert report.unknowns
    assert any("UNKNOWN:" in item for item in report.unknowns)


def test_high_risk_is_highlighted():
    report = AnalystReportGenerator().generate(payload(risks=[{
        "type": "LEVERAGE", "severity": "HIGH", "direction": "NEGATIVE",
        "statement": "Áp lực đòn bẩy tăng.", "evidence_refs": ["fact:debt"], "confidence": "HIGH",
    }]))
    assert report.risks[0].startswith("RISK:")
    assert "đòn bẩy" in report.risks[0]


def test_empty_input_is_safe_fallback():
    empty = {
        "financial_analysis_result": {"executive_summary": [], "financial_trend": [], "profitability_analysis": [], "business_quality": [], "strengths": [], "risks": [], "unknowns": [], "confidence_score": 0},
        "financial_signals": {"signals": [], "overall_assessment": "", "investment_relevance": "", "confidence": 0},
        "benchmark_result": {"company": "UNKNOWN", "benchmarks": [], "relative_assessment": [], "limitations": []},
        "risk_review": {"overall_risk_level": "UNKNOWN", "risks": [], "risk_summary": "", "unknown_risks": [], "confidence": 0},
    }
    report = AnalystReportGenerator().generate(empty)
    assert report.confidence == "LOW"
    assert report.unknowns
    assert "UNKNOWN" in report.executive_summary


def test_report_schema_rejects_extra_fields():
    with pytest.raises(Exception):
        AnalystReport.model_validate({"title": "x", "executive_summary": "x", "financial_assessment": "x", "strengths": [], "weaknesses": [], "risks": [], "benchmark_summary": "x", "unknowns": [], "confidence": "LOW", "evidence_coverage": "LIMITED", "numbers": []})
