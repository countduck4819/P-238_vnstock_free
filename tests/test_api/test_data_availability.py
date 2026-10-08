import pytest

from src.services.data_availability import (
    DataAvailabilityAnalyzer,
    EvidenceRegistry,
    MetricDefinition,
    MetricRegistry,
)
from src.services.evidence_planning import EvidencePlan, EvidencePlanningSkill
from src.services.financial_question_understanding import FinancialQuestionUnderstandingSkill


def test_roe_is_derivable_from_registered_dependencies():
    plan = EvidencePlan.model_validate({
        "objective": "test",
        "evidence_items": [{
            "name": "roe", "category": "DERIVED_METRIC", "priority": "HIGH",
            "source_preference": ["CALCULATION_ENGINE"], "fallback_source": ["POSTGRES"],
            "required": True,
        }],
    })
    report = DataAvailabilityAnalyzer().analyze(plan)
    assert report.missing == []
    assert report.derivable[0].metric == "roe"
    assert report.derivable[0].formula == "net_income / average_equity"
    assert report.derivable[0].dependencies == ["net_profit", "total_equity"]


def test_direct_numeric_and_qualitative_capabilities_are_available():
    blueprint = FinancialQuestionUnderstandingSkill().understand("Thông tin doanh nghiệp của FPT")
    plan = EvidencePlanningSkill().plan(blueprint)
    report = DataAvailabilityAnalyzer().analyze(plan)
    assert any(item.evidence == "company_profile" and item.source == "QDRANT" for item in report.available)

    numeric_plan = EvidencePlan.model_validate({
        "objective": "test",
        "evidence_items": [{
            "name": "profit", "category": "NUMERIC_FACT", "priority": "HIGH",
            "source_preference": ["POSTGRES"], "fallback_source": [], "required": True,
        }],
    })
    numeric_report = DataAvailabilityAnalyzer().analyze(numeric_plan)
    assert numeric_report.available[0].source == "POSTGRES"


def test_missing_is_not_zero_and_external_is_separate():
    plan = EvidencePlan.model_validate({
        "objective": "test",
        "evidence_items": [
            {"name": "cash_flow", "category": "NUMERIC_FACT", "priority": "MEDIUM",
             "source_preference": ["POSTGRES"], "fallback_source": [], "required": True},
            {"name": "current_events", "category": "EXTERNAL_EVENT", "priority": "HIGH",
             "source_preference": ["WEB"], "fallback_source": ["QDRANT"], "required": True},
        ],
    })
    report = DataAvailabilityAnalyzer().analyze(plan)
    assert report.missing[0].evidence == "cash_flow"
    assert report.external_required[0].evidence == "current_events"
    assert all(item.evidence != "cash_flow" for item in report.available)


def test_registries_are_extensible_without_llm_or_data_access():
    metrics = MetricRegistry([MetricDefinition(
        "custom_margin", "custom_profit / custom_revenue", ("custom_profit", "custom_revenue"),
    ), MetricDefinition("custom_profit"), MetricDefinition("custom_revenue")])
    assert metrics.get("custom_margin").dependencies == ("custom_profit", "custom_revenue")
    assert metrics.has_raw("custom_profit") is True
    assert EvidenceRegistry().get("company_profile").source == "QDRANT"


def test_unknown_plan_shape_is_rejected():
    with pytest.raises(Exception):
        DataAvailabilityAnalyzer().analyze({"objective": "x", "evidence_items": [{"name": "x"}]})
