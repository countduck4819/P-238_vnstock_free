"""Compare pre-trained feature experiments on paired OOF rows."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.feature_ablation import (  # noqa: E402
    compare_paired,
    feature_redundancy_metrics,
    load_oof_prediction,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-run", type=Path, required=True)
    parser.add_argument("--candidate", action="append", required=True, help="NAME=MODEL_RUN")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--matrix-config",
        type=Path,
        default=ROOT / "configs/experiments/wave_feature_ablation_v2.yaml",
    )
    args = parser.parse_args()
    base = load_oof_prediction(args.base_run)
    matrix = yaml.safe_load(args.matrix_config.read_text(encoding="utf-8"))
    promotion = matrix["promotion"]
    redundancy_gate = matrix["redundancy"]
    base_features = set(model_dataset_manifest(args.base_run)["feature_columns"])
    reports: dict[str, object] = {}
    args.output.mkdir(parents=True, exist_ok=True)
    for value in args.candidate:
        name, separator, run = value.partition("=")
        if not separator or not name or not run:
            raise ValueError("candidate must use NAME=MODEL_RUN")
        summary, folds = compare_paired(base, load_oof_prediction(Path(run)))
        median_ap_delta = float(folds["delta_average_precision"].median())
        worst_auc_delta = float(folds["delta_roc_auc"].min())
        maximum_missing_rate = model_maximum_feature_missing_rate(Path(run))
        redundancy = model_feature_redundancy(Path(run), base_features)
        checks = {
            "median_ap": median_ap_delta >= promotion["minimum_median_fold_ap_delta"],
            "positive_folds": summary["positive_fold_count_ap"] >= promotion["minimum_positive_fold_count"],
            "worst_auc": worst_auc_delta >= -promotion["maximum_worst_fold_auc_drop"],
            "ece": summary["delta_ece_10_temporal"] <= promotion["maximum_ece_increase"],
            "top5": summary["daily_precision_at_5_relative_gain"]
            >= promotion["minimum_top5_precision_relative_gain"],
            "missing_rate": maximum_missing_rate <= promotion["maximum_feature_missing_rate"],
            "maximum_correlation": redundancy["maximum_absolute_spearman"]
            <= redundancy_gate["maximum_absolute_spearman"],
            "effective_rank": redundancy["effective_rank_fraction"]
            >= redundancy_gate["minimum_effective_rank_fraction"],
        }
        summary["promotion_gate"] = {
            "median_fold_ap_delta": median_ap_delta,
            "minimum_median_fold_ap_delta": promotion["minimum_median_fold_ap_delta"],
            "median_ap_pass": median_ap_delta >= promotion["minimum_median_fold_ap_delta"],
            "positive_fold_count": summary["positive_fold_count_ap"],
            "minimum_positive_fold_count": promotion["minimum_positive_fold_count"],
            "positive_fold_count_pass": summary["positive_fold_count_ap"] >= promotion["minimum_positive_fold_count"],
            "worst_fold_auc_delta": worst_auc_delta,
            "maximum_worst_fold_auc_drop": promotion["maximum_worst_fold_auc_drop"],
            "worst_fold_auc_pass": worst_auc_delta >= -promotion["maximum_worst_fold_auc_drop"],
            "ece_delta": summary["delta_ece_10_temporal"],
            "maximum_ece_increase": promotion["maximum_ece_increase"],
            "top5_precision_relative_gain": summary["daily_precision_at_5_relative_gain"],
            "minimum_top5_precision_relative_gain": promotion[
                "minimum_top5_precision_relative_gain"
            ],
            "maximum_feature_missing_rate_observed": maximum_missing_rate,
            "maximum_feature_missing_rate_allowed": promotion["maximum_feature_missing_rate"],
            "redundancy": redundancy,
            "maximum_absolute_spearman_allowed": redundancy_gate[
                "maximum_absolute_spearman"
            ],
            "minimum_effective_rank_fraction": redundancy_gate[
                "minimum_effective_rank_fraction"
            ],
            "checks": checks,
            "status": "candidate" if all(checks.values()) else "reject_for_next_stage",
        }
        reports[name] = summary
        folds.to_csv(args.output / f"{name}_fold_metrics.csv", index=False)
    (args.output / "summary.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")
    print(json.dumps(reports, indent=2))


def model_maximum_feature_missing_rate(model_run: Path) -> float:
    dataset_manifest = model_dataset_manifest(model_run)
    rates = dataset_manifest.get("feature_null_rates", {})
    return float(max(rates.values(), default=0.0))


def model_dataset_manifest(model_run: Path) -> dict[str, object]:
    model_manifest = json.loads(
        (model_run / "model_manifest.json").read_text(encoding="utf-8")
    )
    dataset_run = Path(model_manifest["dataset_dependency"]["run"])
    return json.loads(
        (dataset_run / "dataset_manifest.json").read_text(encoding="utf-8")
    )


def model_feature_redundancy(
    model_run: Path,
    reference_features: set[str],
    sample_rows: int = 50_000,
) -> dict[str, object]:
    manifest = model_dataset_manifest(model_run)
    model_manifest = json.loads(
        (model_run / "model_manifest.json").read_text(encoding="utf-8")
    )
    dataset_run = Path(model_manifest["dataset_dependency"]["run"])
    feature_columns = list(manifest["feature_columns"])
    parts = sorted((dataset_run / "dataset").glob("year=*/*.parquet"))
    if not parts:
        raise FileNotFoundError(f"No dataset partitions found in {dataset_run}")
    per_part = max(1, sample_rows // len(parts))
    samples = []
    for index, part in enumerate(parts):
        frame = pd.read_parquet(part, columns=feature_columns)
        if len(frame) > per_part:
            frame = frame.sample(per_part, random_state=238 + index)
        samples.append(frame)
    sample = pd.concat(samples, ignore_index=True)
    metrics = feature_redundancy_metrics(
        sample,
        reference_features=reference_features,
    )
    metrics["sample_rows"] = len(sample)
    return metrics


if __name__ == "__main__":
    main()
