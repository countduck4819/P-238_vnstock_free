from src.services.regression_runner import (
    GoldenCase,
    RegressionComparator,
    RegressionReport,
    RegressionRunner,
    load_golden_dataset,
)


def valid_case(**changes):
    data = {
        "id": "g1", "category": "FACT_LOOKUP", "question": "FPT revenue?",
        "expected_intent": "FACT_LOOKUP", "required_evidence": ["revenue"],
        "expected_signals": [], "expected_risks": [], "forbidden_claims": [], "minimum_score": 80,
    }
    data.update(changes)
    return GoldenCase.model_validate(data)


def test_valid_golden_response_passes():
    result = RegressionRunner().evaluate_case(valid_case(), {
        "intent": "FACT_LOOKUP", "text": "FACT: revenue 100 [Evidence: postgres.revenue]",
    })
    assert result.passed
    assert result.score == 100


def test_golden_dataset_has_required_distribution():
    cases = load_golden_dataset("tests/golden_dataset.json")
    assert len(cases) == 100
    counts = {category: sum(item.category == category for item in cases) for category in {
        "FACT_LOOKUP", "TREND_ANALYSIS", "COMPANY_COMPARISON", "FINANCIAL_HEALTH",
        "PROFITABILITY_ANALYSIS", "RISK_ANALYSIS", "MISSING_DATA_HANDLING", "ADVERSARIAL",
    }}
    assert counts == {
        "FACT_LOOKUP": 20, "TREND_ANALYSIS": 15, "COMPANY_COMPARISON": 15,
        "FINANCIAL_HEALTH": 15, "PROFITABILITY_ANALYSIS": 10, "RISK_ANALYSIS": 10,
        "MISSING_DATA_HANDLING": 10, "ADVERSARIAL": 5,
    }


def test_regression_comparator_detects_degradation_and_new_failure():
    previous = RegressionReport(version="1.0", total_cases=2, average_score=90,
                                passed=2, failed=0, case_scores={"a": 90, "b": 90})
    current = RegressionReport(version="1.1", total_cases=3, average_score=80,
                               passed=2, failed=1, case_scores={"a": 70, "b": 95, "c": 60})
    comparison = RegressionComparator().compare(previous, current)
    assert comparison["score_change"] == -10
    assert comparison["degraded_cases"] == ["a"]
    assert comparison["new_failures"] == ["c"]
    assert comparison["regression_detected"]


def test_case_schema_rejects_unknown_field():
    try:
        valid_case(unexpected="value")
    except Exception:
        pass
    else:
        raise AssertionError("unknown fields must be rejected")
