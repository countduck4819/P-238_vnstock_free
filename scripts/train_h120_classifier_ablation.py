"""Train a controlled H120 classifier ablation over locked annual folds."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.train_h120_ranker import DEFAULT_DATASET_RUN, DEFAULT_GROUPS, selected_folds  # noqa: E402
from src.evaluation.wave_model import daily_top_k_metrics  # noqa: E402
from src.training.h120_classifier import attach_v3_label_weights, fit_h120_classifier_fold  # noqa: E402
from src.training.xgboost_pipeline import (  # noqa: E402
    XGBoostTrainingConfig,
    subset_by_keys,
    temporal_calibration_predictions,
)

DEFAULT_LABEL_RUN = Path(
    "data/labels/wave_ignition_snapshot/wave_continuation_h120_v3_eventweights/runs/20260824T054805Z"
)
DEFAULT_CONFIG = Path("configs/wave_continuation_xgboost_h120.yaml")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-run", type=Path, default=DEFAULT_DATASET_RUN)
    parser.add_argument("--label-run", type=Path, default=DEFAULT_LABEL_RUN)
    parser.add_argument("--feature-groups", type=Path, default=DEFAULT_GROUPS)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--feature-group", required=True)
    parser.add_argument("--weight-policy", choices=("baseline", "uniqueness"), required=True)
    parser.add_argument(
        "--random-seed",
        type=int,
        help="Optional confirmation seed; it overrides only the frozen model config seed.",
    )
    parser.add_argument("--folds", default="")
    parser.add_argument("--output-root", type=Path, required=True)
    return parser.parse_args()


def load_dataset(dataset_run: Path, feature_columns: list[str]) -> pd.DataFrame:
    columns = ["symbol", "date", "y_entry", "sample_weight", *feature_columns]
    paths = sorted((dataset_run / "dataset").glob("year=*/dataset.parquet"))
    if not paths:
        raise FileNotFoundError(f"No dataset partitions found under {dataset_run}")
    return pd.concat((pd.read_parquet(path, columns=columns) for path in paths), ignore_index=True)


def load_labels(label_run: Path) -> pd.DataFrame:
    paths = sorted((label_run / "labels").glob("year=*/labels.parquet"))
    if not paths:
        raise FileNotFoundError(f"No label partitions found under {label_run}")
    result = pd.concat(
        (
            pd.read_parquet(
                path,
                columns=["symbol", "date", "y_entry", "event_uniqueness_weight"],
            )
            for path in paths
        ),
        ignore_index=True,
    )
    return result.loc[result["y_entry"].notna()].copy()


def main() -> int:
    args = parse_args()
    groups = json.loads(args.feature_groups.read_text(encoding="utf-8"))
    if args.feature_group not in groups["groups"]:
        raise ValueError(f"Unknown feature group: {args.feature_group}")
    features = list(groups["groups"][args.feature_group])
    dataset_run = args.dataset_run.resolve()
    label_run = args.label_run.resolve()
    dataset, weight_audit = attach_v3_label_weights(
        load_dataset(dataset_run, features), load_labels(label_run), policy=args.weight_policy
    )
    if dataset.duplicated(["symbol", "date"]).any():
        raise RuntimeError("Training dataset has duplicate symbol/date rows.")
    indexed = dataset.set_index(["symbol", "date"], verify_integrity=True)
    config = XGBoostTrainingConfig.from_yaml(args.config)
    if args.random_seed is not None:
        config = replace(config, random_seed=args.random_seed)
    folds = selected_folds(dataset_run, args.folds)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    final = args.output_root.resolve() / "runs" / run_id
    incomplete = final.parent / f".incomplete-{run_id}"
    incomplete.mkdir(parents=True, exist_ok=False)
    oof_parts: list[pd.DataFrame] = []
    fold_records: list[dict[str, object]] = []
    for fold_id in folds:
        split = dataset_run / "splits" / fold_id
        train = subset_by_keys(indexed, split / "train_keys.parquet")
        validation = subset_by_keys(indexed, split / "validation_keys.parquet")
        model, prediction, fold_audit = fit_h120_classifier_fold(train, validation, features, config)
        prediction.insert(0, "fold_id", fold_id)
        (incomplete / "models").mkdir(exist_ok=True)
        model.get_booster().save_model(incomplete / "models" / f"{fold_id}.json")
        oof_parts.append(prediction)
        fold_records.append({"fold_id": fold_id, **fold_audit})
    oof = pd.concat(oof_parts, ignore_index=True).sort_values(["date", "symbol"], kind="stable")
    calibrated, calibration_audit = temporal_calibration_predictions(
        oof,
        clip_epsilon=config.calibration_clip_epsilon,
        random_seed=config.random_seed,
        threshold_grid_size=config.threshold_grid_size,
        top_fraction=config.precision_at_fraction,
    )
    calibrated.rename(columns={"p_entry_calibrated_temporal": "p_h120_calibrated"}, inplace=True)
    daily = daily_top_k_metrics(calibrated, "p_entry_raw", k=10)
    date_fold = calibrated.loc[:, ["date", "fold_id"]].drop_duplicates()
    fold_daily = daily.merge(date_fold, on="date", how="left", validate="one_to_one")
    fold_p10 = {
        str(fold): float(frame["precision_at_k"].mean())
        for fold, frame in fold_daily.groupby("fold_id", observed=True, sort=True)
    }
    (incomplete / "predictions").mkdir(exist_ok=True)
    (incomplete / "audit").mkdir(exist_ok=True)
    calibrated.to_parquet(incomplete / "predictions" / "oof_predictions.parquet", index=False)
    daily.to_csv(incomplete / "audit" / "daily_top10_raw.csv", index=False)
    pd.DataFrame(fold_records).to_csv(incomplete / "audit" / "fold_training.csv", index=False)
    calibration_audit.to_csv(incomplete / "audit" / "calibration_by_fold.csv", index=False)
    manifest = {
        "experiment_type": "controlled_h120_classifier_ablation",
        "run_id": run_id,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "status": "research_only_not_trade_authorized",
        "dataset_run": str(dataset_run),
        "label_run": str(label_run),
        "feature_group": args.feature_group,
        "feature_columns": features,
        "weight_policy": args.weight_policy,
        "weight_audit": weight_audit,
        "folds": folds,
        "configuration": config.to_dict(),
        "raw_p_at_10": float(daily["precision_at_k"].mean()),
        "worst_fold_raw_p_at_10": float(min(fold_p10.values())),
        "fold_raw_p_at_10": fold_p10,
        "final_test_used": False,
    }
    (incomplete / "model_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    incomplete.rename(final)
    print(json.dumps({"run_directory": str(final), **manifest}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
