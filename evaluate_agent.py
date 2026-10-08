"""Run the deterministic FinSight evaluation framework.

Usage:
    python evaluate_agent.py --dataset tests/evaluation_cases.json --responses responses.json

The responses file is a JSON object keyed by case id.  If omitted, empty
responses are evaluated so the command still produces a valid baseline report.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.services.evaluation_framework import EvaluationRunner, load_cases


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate FinSight responses deterministically")
    parser.add_argument("--dataset", default="tests/evaluation_cases.json")
    parser.add_argument("--responses", help="JSON object keyed by evaluation case id")
    parser.add_argument("--output", default="evaluation_report.json")
    args = parser.parse_args()
    cases = load_cases(args.dataset)
    responses = json.loads(Path(args.responses).read_text(encoding="utf-8")) if args.responses else {}
    results, report = EvaluationRunner().evaluate_suite(cases, responses)
    output = {**report.model_dump(), "results": [item.model_dump() for item in results]}
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report.model_dump(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
