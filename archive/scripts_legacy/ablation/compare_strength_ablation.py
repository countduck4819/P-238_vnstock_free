"""Compare conditional-strength OOF heads on identical positive events."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.strength_ablation import compare_strength_paired, load_strength_oof  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-run", type=Path, required=True)
    parser.add_argument("--candidate", action="append", required=True, help="NAME=MODEL_RUN")
    parser.add_argument("--config", type=Path, default=ROOT / "configs/experiments/wave_strength_ablation_v1.yaml")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    matrix = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    baseline = load_strength_oof(str(args.baseline_run / "predictions/oof_predictions.parquet"))
    reports: dict[str, object] = {}
    args.output.mkdir(parents=True, exist_ok=True)
    promotion = matrix["promotion"]
    for item in args.candidate:
        name, separator, run = item.partition("=")
        if not separator or not name or not run:
            raise ValueError("candidate must use NAME=MODEL_RUN")
        summary, folds = compare_strength_paired(
            baseline, load_strength_oof(str(Path(run) / "predictions/oof_predictions.parquet"))
        )
        median_mae_improvement = float((-folds["delta_weighted_mae"] / folds["base_weighted_mae"]).median())
        worst_spearman_drop = float(folds["delta_spearman"].min())
        positive_spearman_folds = int((folds["delta_spearman"] >= 0).sum())
        checks = {
            "mae": median_mae_improvement >= promotion["minimum_median_fold_mae_relative_improvement"],
            "spearman_folds": positive_spearman_folds >= promotion["minimum_positive_spearman_fold_count"],
            "worst_spearman": worst_spearman_drop >= -promotion["maximum_worst_fold_spearman_drop"],
        }
        summary["promotion_gate"] = {
            "median_fold_mae_relative_improvement": median_mae_improvement,
            "positive_spearman_fold_count": positive_spearman_folds,
            "worst_fold_spearman_delta": worst_spearman_drop,
            "checks": checks,
            "status": "candidate" if all(checks.values()) else "reject_for_next_stage",
        }
        reports[name] = summary
        folds.to_csv(args.output / f"{name}_fold_metrics.csv", index=False)
    (args.output / "summary.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
