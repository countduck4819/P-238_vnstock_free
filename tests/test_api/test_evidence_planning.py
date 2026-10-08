import pytest

from src.services.evidence_planning import (
    EvidenceCategory,
    EvidencePlan,
    EvidencePlanningSkill,
)
from src.services.financial_question_understanding import FinancialQuestionUnderstandingSkill


def test_health_blueprint_maps_to_ordered_source_plan():
    blueprint = FinancialQuestionUnderstandingSkill().understand("FPT đang khỏe lên hay yếu đi?")
    plan = EvidencePlanningSkill().plan(blueprint)
    assert plan.objective.startswith("Collect evidence for FINANCIAL_HEALTH_ANALYSIS")
    names = [item.name for item in plan.evidence_items]
    assert names[:2] == ["revenue_growth", "profit_growth"]
    growth = plan.evidence_items[0]
    assert growth.category == EvidenceCategory.DERIVED_METRIC
    assert growth.source_preference == ["CALCULATION_ENGINE"]
    assert growth.fallback_source == ["POSTGRES"]
    assert all(item.required for item in plan.evidence_items)


def test_numeric_qualitative_and_external_categories_use_ontology_sources():
    blueprint = {
        "intent": "RISK_ANALYSIS", "companies": ["FPT"], "sector": ["CORPORATE"],
        "period": {"start": "2024", "end": "2024"}, "analysis_type": ["industry_context"],
        "required_evidence": [
            {"name": "revenue", "type": "NUMERIC"},
            {"name": "business_driver", "type": "QUALITATIVE"},
            {"name": "current_events", "type": "EXTERNAL"},
        ], "risk_flags": [],
    }
    items = EvidencePlanningSkill().plan(blueprint).evidence_items
    assert items[0].category == EvidenceCategory.NUMERIC_FACT
    assert items[0].source_preference == ["POSTGRES"]
    assert items[1].category == EvidenceCategory.QUALITATIVE_KNOWLEDGE
    assert items[1].source_preference == ["QDRANT"]
    assert items[2].category == EvidenceCategory.EXTERNAL_EVENT
    assert items[2].source_preference == ["WEB"]


def test_planner_does_not_accept_unknown_metric_or_extra_field():
    with pytest.raises(Exception):
        EvidencePlanningSkill().plan({
            "intent": "FACT_LOOKUP", "companies": ["FPT"], "sector": [],
            "period": {"start": "2024", "end": "2024"}, "analysis_type": [],
            "required_evidence": [{"name": "invented_metric", "type": "NUMERIC"}],
            "risk_flags": [],
        })
    with pytest.raises(Exception):
        EvidencePlan.model_validate({"objective": "x", "evidence_items": [], "answer": "no"})


def test_plan_is_pure_and_does_not_require_data_clients():
    plan = EvidencePlanningSkill().plan({
        "intent": "FACT_LOOKUP", "companies": ["FPT"], "sector": [],
        "period": {"start": "2024", "end": "2024"}, "analysis_type": [],
        "required_evidence": [{"name": "profit", "type": "NUMERIC"}], "risk_flags": [],
    })
    assert plan.evidence_items[0].category == "NUMERIC_FACT"

