import json

import pytest

from src.services.agent_graph import FinancialAgentGraph
from src.services.agent_planner import StructuredAgentPlanner
from src.services.financial_question_understanding import (
    FinancialAnalysisBlueprint,
    FinancialQuestionUnderstandingSkill,
)


class FailingLLM:
    def generate(self, system_prompt, user_prompt):
        raise RuntimeError("provider unavailable")


class InvalidLLM:
    def generate(self, system_prompt, user_prompt):
        return json.dumps({
            "intent": "FACT_LOOKUP",
            "companies": ["NOT_A_TICKER"],
            "sector": [],
            "period": {"start": "2024", "end": "2024"},
            "analysis_type": [],
            "required_evidence": [{"name": "made_up_metric", "type": "NUMERIC"}],
            "risk_flags": [],
        })


def test_fact_blueprint_is_answer_free_and_grounded():
    blueprint = FinancialQuestionUnderstandingSkill().understand("Doanh thu của FPT năm 2024")
    assert blueprint.intent.value == "FACT_LOOKUP"
    assert blueprint.companies == ["FPT"]
    assert blueprint.period.model_dump() == {"start": "2024", "end": "2024"}
    assert {item.name for item in blueprint.required_evidence} == {"revenue"}
    assert all(not hasattr(item, "value") for item in blueprint.required_evidence)


def test_health_question_requires_multiple_evidence_types():
    blueprint = FinancialQuestionUnderstandingSkill().understand("FPT đang khỏe lên hay yếu đi?")
    assert blueprint.intent.value == "FINANCIAL_HEALTH_ANALYSIS"
    assert {"growth", "profitability", "efficiency"}.issubset(blueprint.analysis_type)
    assert any(item.name == "business_driver" and item.type == "QUALITATIVE" for item in blueprint.required_evidence)


def test_bank_period_and_ranking_are_structured():
    blueprint = FinancialQuestionUnderstandingSkill().understand(
        "Xếp hạng 5 ngân hàng có lợi nhuận sau thuế năm 2024"
    )
    assert blueprint.intent.value == "COMPANY_COMPARISON"
    assert blueprint.sector == ["BANK"]
    assert blueprint.period.end == "2024"
    assert "COMPANY_RESOLVED_FROM_RANK_RESULT" in blueprint.risk_flags


def test_llm_failure_uses_deterministic_fallback():
    skill = FinancialQuestionUnderstandingSkill(FailingLLM())
    blueprint = skill.understand("Doanh thu FPT năm 2024")
    assert blueprint.companies == ["FPT"]
    assert skill.last_used_llm is False
    assert skill.last_failure.startswith("QUESTION_UNDERSTANDING_LLM_FAILURE")


def test_invalid_llm_output_cannot_invent_company_or_metric():
    skill = FinancialQuestionUnderstandingSkill(InvalidLLM())
    blueprint = skill.understand("Doanh thu FPT năm 2024")
    assert blueprint.companies == ["FPT"]
    assert all(item.name != "made_up_metric" for item in blueprint.required_evidence)
    assert skill.last_used_llm is False


def test_schema_rejects_extra_fields_and_unknown_evidence():
    with pytest.raises(Exception):
        FinancialAnalysisBlueprint.model_validate({
            "intent": "FACT_LOOKUP", "companies": [], "sector": [],
            "period": {"start": "", "end": ""}, "analysis_type": [],
            "required_evidence": [{"name": "unknown", "type": "NUMERIC"}],
            "risk_flags": [], "answer": "must not be accepted",
        })


def test_langgraph_node_only_builds_blueprint_without_tools():
    graph = FinancialAgentGraph(object(), StructuredAgentPlanner(None))
    output = graph.understand_question({
        "question": "Doanh thu FPT năm 2024",
        "trace": [], "warnings": [], "llm_call_count": 0, "max_llm_calls": 5,
    })
    assert output["blueprint_used"] is True
    assert output["financial_blueprint"]["companies"] == ["FPT"]
    assert output["financial_blueprint"]["period"]["end"] == "2024"
    assert output["trace"][0]["node"] == "understand_question"
