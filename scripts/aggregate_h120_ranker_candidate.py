"""Aggregate a frozen-candidate seed confirmation without pooling dates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.h120_ranker_reporting import summarize_seed_metric_reports
from src.training.h120_experiment_protocol import H120ExperimentProtocol


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--seed-metrics", type=Path, nargs="+", required=True)
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
        reports[seed] = payload
    missing = sorted(set(protocol.confirmation_seeds).difference(reports))
    if missing:
        raise ValueError(f"Seed confirmation is incomplete: {missing}")
    ranking = summarize_seed_metric_reports(
        {seed: payload["ranker"]["daily_metrics"] for seed, payload in reports.items()}
    )
    protocol.validate_selection_folds(ranking["folds"])
    moving_lowers = {
        seed: float(payload["paired"]["precision_at_k_moving_block_bootstrap"]["lower"])
        for seed, payload in reports.items()
    }
    fold_deltas = {
        seed: {
            fold: float(value) - float(payload["baseline"]["fold_p_at_10"][fold])
            for fold, value in payload["ranker"]["fold_p_at_10"].items()
        }
        for seed, payload in reports.items()
    }
    challenger_fold_lifts = {
        seed: payload["ranker"]["daily_metrics"]["lift"]["fold_means"]
        for seed, payload in reports.items()
    }
    gates = {
        "all_seed_moving_block_ci_lower_positive": all(value > 0.0 for value in moving_lowers.values()),
        "worst_fold_lift_at_least_1_10": ranking["lift"]["worst_fold_over_seeds"] >= 1.10,
        "no_challenger_fold_lift_below_1": all(
            float(value) >= 1.0
            for per_seed in challenger_fold_lifts.values()
            for value in per_seed.values()
        ),
        "calibration_is_separate_gate": True,
    }
    output = {
        "status": "candidate_seed_confirmation_research_only",
        "protocol": protocol.to_manifest(),
        "ranking_seed_summary": ranking,
        "moving_block_ci_lower_by_seed": moving_lowers,
        "fold_p10_delta_by_seed": fold_deltas,
        "challenger_fold_lift_by_seed": challenger_fold_lifts,
        "diagnostics": {
            "all_seed_fold_p10_deltas_positive": all(
                value > 0.0 for per_seed in fold_deltas.values() for value in per_seed.values()
            ),
            "minimum_seed_fold_p10_delta": min(
                value for per_seed in fold_deltas.values() for value in per_seed.values()
            ),
        },
        "gates": gates,
        "research_freeze_recommended": all(
            value for name, value in gates.items() if name != "calibration_is_separate_gate"
        ),
        "production_promotion_recommended": False,
        "trade_authorized": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
