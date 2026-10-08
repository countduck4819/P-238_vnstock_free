"""Run FinSight golden-dataset regression evaluation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from src.services.regression_runner import RegressionComparator, RegressionReport, RegressionRunner, load_golden_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic FinSight regression evaluation")
    parser.add_argument("--dataset", default="tests/golden_dataset.json")
    parser.add_argument("--responses", help="JSON object keyed by golden case id")
    parser.add_argument("--previous", help="Previous RegressionReport JSON for comparison")
    parser.add_argument("--config", default="evaluation_config.yaml")
    parser.add_argument("--version", default="1.0")
    parser.add_argument("--output", default="regression_report.json")
    args = parser.parse_args()
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    cases = load_golden_dataset(args.dataset)
    responses: dict[str, Any] = json.loads(Path(args.responses).read_text(encoding="utf-8")) if args.responses else {}
    results, report = RegressionRunner(args.version).run(cases, responses)
    comparison = None
    if args.previous:
        previous = RegressionReport.model_validate_json(Path(args.previous).read_text(encoding="utf-8"))
        comparison = RegressionComparator().compare(previous, report)
        report.regressions = comparison["affected_cases"] if comparison["regression_detected"] else []
    threshold_failures = []
    if report.average_score < float(config["minimum_average_score"]):
        threshold_failures.append("average_score")
    if any(score < float(config["minimum_module_score"]) for score in report.module_scores.values()):
        threshold_failures.append("module_score")
    if comparison and comparison["score_change"] < -float(config["maximum_regression_drop"]):
        threshold_failures.append("regression_drop")
    output = {**report.model_dump(), "threshold_failures": threshold_failures, "comparison": comparison,
              "case_results": [item.model_dump() for item in results]}
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Regression Report:\nFinSight Version: {report.version}\nTotal Cases: {report.total_cases}\n"
          f"Score: {report.average_score}/100\nPassed: {report.passed}\nFailed: {report.failed}")
    if threshold_failures:
        print("Threshold failures: " + ", ".join(threshold_failures))
    return 1 if threshold_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
