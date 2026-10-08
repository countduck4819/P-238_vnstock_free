"""Aggregate registered R2 seed reports and enforce the Phase-C fold contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.h120_ranker_reporting import summarize_seed_metric_reports  # noqa: E402
from src.training.h120_experiment_protocol import H120ExperimentProtocol  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument(
        "--seed-metrics",
        type=Path,
        nargs="+",
        required=True,
        help="One metrics.json from each R2 confirmation seed.",
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    protocol = H120ExperimentProtocol.from_yaml(args.protocol)
    reports: dict[int, dict] = {}
    for path in args.seed_metrics:
        payload = json.loads(path.read_text(encoding="utf-8"))
        seed = int(payload["random_seed"])
        if seed in reports:
            raise ValueError(f"Duplicate seed metrics: {seed}")
        reports[seed] = payload["ranker"]["daily_metrics"]
    missing_seeds = sorted(set(protocol.confirmation_seeds).difference(reports))
    if missing_seeds:
        raise ValueError(f"R2 is incomplete; missing confirmation seeds: {missing_seeds}")
    summary = summarize_seed_metric_reports(reports)
    protocol.validate_selection_folds(summary["folds"])
    output = {
        "status": "phase_c_r2_complete_research_only",
        "protocol": protocol.to_manifest(),
        "seed_summary": summary,
        "trade_authorized": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
