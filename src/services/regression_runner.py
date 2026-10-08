"""Deterministic golden-dataset regression evaluation for FinSight."""
from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.services.evaluation_framework import EvaluationRunner


class GoldenCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    category: str
    question: str
    expected_intent: str = ""
    required_evidence: list[str] = Field(default_factory=list)
    expected_signals: list[str] = Field(default_factory=list)
    expected_risks: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    minimum_score: float = Field(default=80, ge=0, le=100)


class RegressionCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    score: float
    passed: bool
    issues: list[str] = Field(default_factory=list)


class RegressionReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str
    total_cases: int = 0
    average_score: float = 0
    passed: int = 0
    failed: int = 0
    regressions: list[str] = Field(default_factory=list)
    module_scores: dict[str, float] = Field(default_factory=dict)
    case_scores: dict[str, float] = Field(default_factory=dict)


class RegressionRunner:
    """Score golden cases without invoking the agent or external services."""

    def __init__(self, version: str = "1.0") -> None:
        self.version = version
        self.evaluator = EvaluationRunner()

    def evaluate_case(self, case: GoldenCase | Mapping[str, Any], response: Any) -> RegressionCaseResult:
        golden = case if isinstance(case, GoldenCase) else GoldenCase.model_validate(case)
        base = self.evaluator.evaluate({
            "id": golden.id,
            "question": golden.question,
            "category": "FACT_LOOKUP",
            "expected_intent": golden.expected_intent,
            "required_evidence": golden.required_evidence,
            "forbidden_claims": golden.forbidden_claims,
            "expected_behaviors": [],
        }, response)
        text = self._text(response)
        issues = list(base.issues)
        for signal in golden.expected_signals:
            if signal.casefold().replace("_", " ") not in text and signal.casefold() not in text:
                issues.append(f"SIGNAL: missing expected signal: {signal}")
        for risk in golden.expected_risks:
            if risk.casefold().replace("_", " ") not in text and risk.casefold() not in text:
                issues.append(f"RISK: missing expected risk: {risk}")
        score = base.score
        expected_total = len(golden.expected_signals) + len(golden.expected_risks)
        if expected_total:
            matched = expected_total - sum(issue.startswith(("SIGNAL:", "RISK:")) for issue in issues)
            score = round((base.score * 0.75) + (100 * matched / expected_total * 0.25), 2)
        passed = score >= golden.minimum_score and not any(
            issue.startswith(("HALLUCINATION:", "SAFETY:")) for issue in issues
        )
        return RegressionCaseResult(case_id=golden.id, score=score, passed=passed,
                                    issues=list(dict.fromkeys(issues)))

    def run(self, cases: list[GoldenCase], responses: Mapping[str, Any]) -> tuple[list[RegressionCaseResult], RegressionReport]:
        results = [self.evaluate_case(case, responses.get(case.id)) for case in cases]
        category_scores: dict[str, list[float]] = {}
        for case, result in zip(cases, results):
            category_scores.setdefault(case.category, []).append(result.score)
        module_scores = {
            self._module_for_category(category): round(sum(scores) / len(scores), 2)
            for category, scores in category_scores.items()
        }
        report = RegressionReport(
            version=self.version,
            total_cases=len(results),
            average_score=round(sum(item.score for item in results) / len(results), 2) if results else 0,
            passed=sum(item.passed for item in results),
            failed=sum(not item.passed for item in results),
            module_scores=module_scores,
            case_scores={item.case_id: item.score for item in results},
        )
        return results, report

    @staticmethod
    def _text(response: Any) -> str:
        if isinstance(response, str):
            return response.casefold()
        if isinstance(response, Mapping):
            return " ".join(f"{key} {RegressionRunner._text(value)}" for key, value in response.items())
        if isinstance(response, list):
            return " ".join(RegressionRunner._text(item) for item in response)
        return "" if response is None else str(response).casefold()

    @staticmethod
    def _module_for_category(category: str) -> str:
        return {
            "FACT_LOOKUP": "question_understanding",
            "TREND_ANALYSIS": "reasoning",
            "COMPANY_COMPARISON": "benchmark",
            "FINANCIAL_HEALTH": "reasoning",
            "PROFITABILITY_ANALYSIS": "interpretation",
            "RISK_ANALYSIS": "risk_review",
            "MISSING_DATA_HANDLING": "availability",
            "EXTERNAL_RESEARCH": "external_recovery",
            "ADVERSARIAL": "report_generation",
        }.get(category, "unknown")


class RegressionComparator:
    def compare(self, previous: RegressionReport | Mapping[str, Any], current: RegressionReport | Mapping[str, Any]) -> dict[str, Any]:
        old = previous if isinstance(previous, RegressionReport) else RegressionReport.model_validate(previous)
        new = current if isinstance(current, RegressionReport) else RegressionReport.model_validate(current)
        old_scores, new_scores = old.case_scores, new.case_scores
        common = set(old_scores) & set(new_scores)
        improved = sorted(case for case in common if new_scores[case] > old_scores[case])
        degraded = sorted(case for case in common if new_scores[case] < old_scores[case])
        new_failures = sorted({
            case for case in new_scores if new_scores[case] < 80 and case not in old_scores
        })
        return {
            "score_change": round(new.average_score - old.average_score, 2),
            "improvement": f"{new.average_score - old.average_score:+.2f}",
            "improved_cases": improved,
            "degraded_cases": degraded,
            "new_failures": new_failures,
            "regression_detected": new.average_score < old.average_score,
            "affected_cases": degraded + new_failures,
        }


def load_golden_dataset(path: str | Path) -> list[GoldenCase]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [GoldenCase.model_validate(item) for item in data]
