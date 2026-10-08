"""Train the stock-only H120 XGBRanker on locked walk-forward folds."""

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

from src.evaluation.wave_model import daily_top_k_metrics  # noqa: E402
from src.training.h120_ranker import H120RankerConfig, fit_h120_ranker_fold  # noqa: E402
from src.training.h120_experiment_protocol import H120ExperimentProtocol  # noqa: E402
from src.training.xgboost_pipeline import (  # noqa: E402
    subset_by_keys,
    temporal_calibration_predictions,
)

DEFAULT_DATASET_RUN = Path(
    "data/training/wave_ignition_snapshot/wave_dataset_continuation_h120/runs/20260823T050830Z"
)
DEFAULT_GROUPS = Path("reports/h120_improvement/feature_governance/feature_groups_resolved.json")
DEFAULT_CONFIG = Path("configs/experiments/h120_ranker_stock_primitives_v1.yaml")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-run", type=Path, default=DEFAULT_DATASET_RUN)
    parser.add_argument("--feature-groups", type=Path, default=DEFAULT_GROUPS)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("models/wave_ignition/h120_ranker_stock_primitives_v1"),
    )
    parser.add_argument("--folds", default="", help="Optional comma-separated fold IDs.")
    parser.add_argument(
        "--protocol",
        type=Path,
        help="Optional frozen generation protocol; validates the actual dataset label version.",
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        help="Optional confirmation seed; it overrides only the frozen config seed.",
    )
    return parser.parse_args()


def load_dataset(
    dataset_run: Path,
    feature_columns: list[str],
    *,
    extra_columns: tuple[str, ...] = (),
) -> pd.DataFrame:
    columns = list(dict.fromkeys(["symbol", "date", "y_entry", "sample_weight", *feature_columns, *extra_columns]))
    paths = sorted((dataset_run / "dataset").glob("year=*/dataset.parquet"))
    if not paths:
        raise FileNotFoundError(f"No dataset partitions found under {dataset_run}")
    frame = pd.concat((pd.read_parquet(path, columns=columns) for path in paths), ignore_index=True)
    frame["date"] = pd.to_datetime(frame["date"], errors="raise")
    if frame.duplicated(["symbol", "date"]).any():
        raise RuntimeError("Dataset has duplicate symbol/date rows.")
    return frame.set_index(["symbol", "date"], verify_integrity=True)


def selected_folds(dataset_run: Path, requested: str) -> list[str]:
    available = sorted(path.name for path in (dataset_run / "splits").glob("fold_*"))
    if not requested.strip():
        return available
    wanted = [value.strip() for value in requested.split(",") if value.strip()]
    missing = sorted(set(wanted).difference(available))
    if missing:
        raise ValueError(f"Unknown folds: {missing}; available: {available}")
    return wanted


def main() -> int:
    args = parse_args()
    dataset_run = args.dataset_run.resolve()
    if args.protocol is not None:
        H120ExperimentProtocol.from_yaml(args.protocol).validate_dataset_manifest(dataset_run)
    groups = json.loads(args.feature_groups.read_text(encoding="utf-8"))
    config = H120RankerConfig.from_yaml(args.config)
    if args.random_seed is not None:
        config = replace(config, random_seed=args.random_seed)
    group_name = "stock_primitives"
    feature_columns = list(groups["groups"][group_name])
    regime_column = "market_regime_score"
    dataset = load_dataset(dataset_run, feature_columns, extra_columns=(regime_column,))
    folds = selected_folds(dataset_run, args.folds)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    final = args.output_root.resolve() / "runs" / run_id
    incomplete = final.parent / f".incomplete-{run_id}"
    incomplete.mkdir(parents=True, exist_ok=False)
    oof_parts: list[pd.DataFrame] = []
    for fold_id in folds:
        split = dataset_run / "splits" / fold_id
        train = subset_by_keys(dataset, split / "train_keys.parquet")
        validation = subset_by_keys(dataset, split / "validation_keys.parquet")
        model, prediction = fit_h120_ranker_fold(train, validation, feature_columns, config)
        prediction = prediction.merge(
            validation.loc[:, ["symbol", "date", "sample_weight", regime_column]],
            on=["symbol", "date"],
            how="left",
            validate="one_to_one",
        )
        prediction["fold_id"] = fold_id
        (incomplete / "models").mkdir(exist_ok=True)
        model.get_booster().save_model(incomplete / "models" / f"{fold_id}.json")
        oof_parts.append(prediction)
    oof = pd.concat(oof_parts, ignore_index=True).sort_values(["date", "symbol"], kind="stable")
    oof["p_entry_raw"] = oof["p_rank_raw"]
    calibrated, calibration_audit = temporal_calibration_predictions(
        oof,
        clip_epsilon=1e-6,
        random_seed=config.random_seed,
        threshold_grid_size=401,
        top_fraction=0.05,
    )
    calibrated.rename(
        columns={
            "p_entry_calibrated_temporal": "p_h120_calibrated",
        },
        inplace=True,
    )
    calibrated["calibration_is_temporal"] = calibrated["p_h120_calibrated"].notna()
    (incomplete / "predictions").mkdir(exist_ok=True)
    calibrated.to_parquet(incomplete / "predictions" / "oof_ranker_predictions.parquet", index=False)
    calibration_audit.to_csv(incomplete / "calibration_by_fold.csv", index=False)
    daily_top_k_metrics(calibrated, "rank_score", k=10).to_csv(
        incomplete / "daily_top10_rank_score.csv", index=False
    )
    manifest = {
        "model_version": config.model_version,
        "run_id": run_id,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "dataset_run": str(dataset_run),
        "folds": folds,
        "feature_group": group_name,
        "feature_columns": feature_columns,
        "configuration": config.to_dict(),
        "output_contract": {
            "ranking_output": "rank_score",
            "ranking_policy": "Top-10 order comes only from rank_score.",
            "probability_output": "p_h120_calibrated",
            "probability_policy": "Causal Platt calibration over prior OOF folds only.",
        },
        "weight_policy": "No classifier class/sample weight is passed to pairwise ranker.",
        "status": "research_only_not_trade_authorized",
    }
    (incomplete / "model_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    incomplete.rename(final)
    print(json.dumps({"status": "ok", "run_directory": str(final), "folds": folds}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
