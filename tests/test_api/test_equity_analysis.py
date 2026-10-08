import pytest

from src.services.equity_analysis import EquityAnalysisNode, EquityAnalysisReport


def test_report_separates_facts_and_inferences_with_references():
    report = EquityAnalysisNode().analyze({
        "facts": [{"metric": "ROE", "value": 0.24, "year": 2024, "source": "POSTGRESQL", "confidence": "HIGH"}],
        "interpretations": [{"text": "Doanh nghiệp tập trung vào công nghệ.", "source": "QDRANT", "confidence": "LOW"}],
        "confidence": "HIGH", "limitations": [], "conflict": False, "conflicts": [],
    })
    assert report.executive_summary[0].kind.value == "INFERENCE"
    assert report.executive_summary[0].evidence_refs
    assert report.financial_trend[0].kind.value == "UNKNOWN"
    assert report.business_quality[0].kind.value == "FACT"
    assert report.confidence_score == "HIGH"


def test_conflicts_are_explicitly_reported_as_risk():
    report = EquityAnalysisNode().analyze({
        "facts": [{"metric": "ROE", "value": 0.24, "year": 2024, "source": "POSTGRESQL", "confidence": "HIGH"}],
        "interpretations": [], "confidence": "LOW",
        "limitations": ["Evidence conflict detected for roe:2024"], "conflict": True,
        "conflicts": [{"key": "roe:2024", "selected_source": "POSTGRESQL", "candidates": []}],
    })
    assert any(item.kind.value == "INFERENCE" for item in report.risk)
    assert report.risk[0].evidence_refs == ["conflict:roe:2024"]


def test_empty_package_reports_unknown_without_inventing_values():
    report = EquityAnalysisNode().analyze({
        "facts": [], "interpretations": [], "confidence": "LOW",
        "limitations": [], "conflict": False, "conflicts": [],
    })
    assert report.executive_summary[0].kind.value == "UNKNOWN"
    assert all("0" not in item.text for item in report.missing_information)


def test_claims_without_references_are_rejected():
    with pytest.raises(Exception):
        EquityAnalysisReport.model_validate({
            "executive_summary": [{"kind": "FACT", "text": "ROE là 24%", "evidence_refs": []}],
            "financial_trend": [], "business_quality": [], "strength": [], "risk": [],
            "missing_information": [], "confidence_score": "HIGH",
        })

