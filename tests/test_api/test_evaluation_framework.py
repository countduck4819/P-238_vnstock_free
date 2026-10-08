import pytest

from src.services.evaluation_framework import (
    EvaluationCase,
    EvaluationCategory,
    EvaluationRunner,
    load_cases,
)


def case(**overrides):
    data = {
        "id": "case",
        "question": "FPT question",
        "category": "FACT_LOOKUP",
        "expected_intent": "FACT_LOOKUP",
        "required_evidence": ["revenue"],
        "forbidden_claims": [],
        "expected_behaviors": ["fact"],
    }
    data.update(overrides)
    return EvaluationCase.model_validate(data)


def test_valid_response_passes():
    result = EvaluationRunner().evaluate(case(), {
        "intent": "FACT_LOOKUP",
        "text": "FACT: revenue is reported [Evidence: postgres.revenue]",
    })
    assert result.passed
    assert result.score == 100


def test_missing_evidence_fails_completeness():
    result = EvaluationRunner().evaluate(case(required_evidence=["revenue", "profit_growth"]), {
        "intent": "FACT_LOOKUP", "text": "FACT: revenue [Evidence: db.revenue]",
    })
    assert not result.passed
    assert result.completeness_score == 50
    assert any("missing required evidence" in issue for issue in result.issues)


def test_hallucinated_number_fails_grounding():
    result = EvaluationRunner().evaluate(case(required_evidence=[]), {
        "intent": "FACT_LOOKUP", "text": "FACT: doanh thu là 999 tỷ đồng",
    })
    assert not result.passed
    assert result.hallucination_score == 0


def test_forbidden_investment_advice_fails_safety():
    result = EvaluationRunner().evaluate(case(), {
        "intent": "FACT_LOOKUP", "text": "FACT: revenue [Evidence: db] nên mua ngay",
    })
    assert not result.passed
    assert result.safety_score == 0


def test_empty_response_is_safe_fallback():
    result = EvaluationRunner().evaluate(case(), "")
    assert not result.passed
    assert result.score == 0
    assert any("empty response" in issue for issue in result.issues)


def test_suite_report_and_dataset_counts():
    cases = load_cases("tests/evaluation_cases.json")
    assert len(cases) == 20
    assert sum(item.category == EvaluationCategory.FACT_LOOKUP for item in cases) == 5
    results, report = EvaluationRunner().evaluate_suite(cases, {})
    assert len(results) == 20
    assert report.total_cases == 20
    assert len(report.failed_cases) == 20
    assert set(report.module_quality) == {"question_understanding", "evidence_planning", "reasoning", "risk_review"}


def test_case_schema_rejects_unknown_field():
    with pytest.raises(Exception):
        case(unexpected="field")
