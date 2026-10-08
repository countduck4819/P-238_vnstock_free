"""Train a classifier-only structural-breakdown head with causal OOF calibration."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from xgboost import XGBClassifier

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.training import (  # noqa: E402
    XGBoostTrainingConfig,
    fit_sigmoid_calibration,
    median_best_round,
    select_f1_threshold,
    subset_by_keys,
    temporal_calibration_predictions,
    weighted_class_ratio,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-run", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--output-root", type=Path, default=Path("models/wave_ignition")
    )
    return parser.parse_args()


def load_dataset(run: Path) -> pd.DataFrame:
    paths = sorted(run.glob("dataset/year=*/dataset.parquet"))
    if not paths:
        raise FileNotFoundError(f"No dataset partitions found in {run}")
    frame = pd.concat((pd.read_parquet(path) for path in paths), ignore_index=True)
    frame["date"] = pd.to_datetime(frame["date"], errors="raise")
    frame.set_index(["symbol", "date"], verify_integrity=True, inplace=True)
    return frame.sort_index()


def feature_matrix(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    return frame.loc[:, columns].astype("float32")


def parameters(config: XGBoostTrainingConfig, ratio: float, rounds: int | None = None) -> dict:
    values = dict(config.classifier)
    if rounds is not None:
        values["n_estimators"] = rounds
        values.pop("early_stopping_rounds", None)
    values.update(
        random_state=config.random_seed,
        n_jobs=config.n_jobs,
        scale_pos_weight=ratio,
        verbosity=0,
    )
    return values


def best_round(model: XGBClassifier, fallback: int) -> int:
    try:
        return int(model.best_iteration) + 1
    except (AttributeError, TypeError):
        return int(fallback)


def normalize(value):
    if isinstance(value, dict):
        return {str(key): normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if not np.isfinite(value) else float(value)
    return value


def write_json(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(normalize(payload), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main() -> None:
    args = parse_args()
    dataset_run = args.dataset_run.resolve()
    config = XGBoostTrainingConfig.from_yaml(args.config)
    manifest = json.loads(
        (dataset_run / "dataset_manifest.json").read_text(encoding="utf-8")
    )
    feature_columns = list(manifest["feature_columns"])
    dataset = load_dataset(dataset_run)
    prediction_frames: list[pd.DataFrame] = []
    rounds: list[int] = []
    raw_fold_rows: list[dict[str, object]] = []
    fold_dirs = sorted(
        path for path in (dataset_run / "splits").glob("fold_*") if path.is_dir()
    )
    for fold_dir in fold_dirs:
        train = subset_by_keys(dataset, fold_dir / "train_keys.parquet")
        validation = subset_by_keys(dataset, fold_dir / "validation_keys.parquet")
        if train["y_entry"].nunique() < 2 or validation["y_entry"].nunique() < 2:
            raise RuntimeError(f"{fold_dir.name} does not contain both classes.")
        ratio = weighted_class_ratio(train["y_entry"], train["sample_weight"])
        model = XGBClassifier(**parameters(config, ratio))
        model.fit(
            feature_matrix(train, feature_columns),
            train["y_entry"].astype("int8"),
            sample_weight=train["sample_weight"].astype(float),
            eval_set=[
                (
                    feature_matrix(validation, feature_columns),
                    validation["y_entry"].astype("int8"),
                )
            ],
            sample_weight_eval_set=[validation["sample_weight"].astype(float)],
            verbose=False,
        )
        probability = model.predict_proba(feature_matrix(validation, feature_columns))[:, 1]
        selected_round = best_round(model, int(config.classifier["n_estimators"]))
        rounds.append(selected_round)
        prediction = validation[["symbol", "date", "y_entry", "sample_weight"]].copy()
        prediction.insert(0, "fold_id", fold_dir.name)
        prediction["p_entry_raw"] = probability
        prediction_frames.append(prediction)
        raw_fold_rows.append({
            "fold_id": fold_dir.name,
            "rows": int(len(validation)),
            "positive_rate": float(np.average(validation["y_entry"], weights=validation["sample_weight"])),
            "average_precision_raw": float(average_precision_score(
                validation["y_entry"], probability, sample_weight=validation["sample_weight"]
            )),
            "roc_auc_raw": float(roc_auc_score(
                validation["y_entry"], probability, sample_weight=validation["sample_weight"]
            )),
            "brier_raw": float(brier_score_loss(
                validation["y_entry"], probability, sample_weight=validation["sample_weight"]
            )),
            "best_round": selected_round,
        })

    oof = pd.concat(prediction_frames, ignore_index=True)
    oof, temporal_audit = temporal_calibration_predictions(
        oof,
        clip_epsilon=config.calibration_clip_epsilon,
        random_seed=config.random_seed,
        threshold_grid_size=config.threshold_grid_size,
        top_fraction=config.precision_at_fraction,
    )
    oof["y_breakdown"] = oof["y_entry"].astype("int8")
    oof["p_breakdown"] = oof["p_entry_calibrated_temporal"]
    valid = oof["p_breakdown"].notna()
    last_threshold = float(oof.loc[valid, "temporal_threshold"].dropna().iloc[-1])
    y_valid = oof.loc[valid, "y_entry"]
    p_valid = oof.loc[valid, "p_breakdown"]
    w_valid = oof.loc[valid, "sample_weight"]
    oof_metrics = {
        "rows": int(valid.sum()),
        "positive_rate": float(np.average(y_valid, weights=w_valid)),
        "average_precision": float(average_precision_score(y_valid, p_valid, sample_weight=w_valid)),
        "roc_auc": float(roc_auc_score(y_valid, p_valid, sample_weight=w_valid)),
        "brier_score": float(brier_score_loss(y_valid, p_valid, sample_weight=w_valid)),
        "deployment_threshold_from_last_causal_fold": last_threshold,
    }

    deployment_calibrator = fit_sigmoid_calibration(
        oof["p_entry_raw"],
        oof["y_entry"],
        oof["sample_weight"],
        clip_epsilon=config.calibration_clip_epsilon,
        random_seed=config.random_seed,
    )
    calibrated_oof = deployment_calibrator.predict(oof["p_entry_raw"])
    deployment_threshold, _ = select_f1_threshold(
        oof["y_entry"],
        calibrated_oof,
        oof["sample_weight"],
        grid_size=config.threshold_grid_size,
    )
    final_train = subset_by_keys(dataset, dataset_run / "splits/final/train_keys.parquet")
    ratio = weighted_class_ratio(final_train["y_entry"], final_train["sample_weight"])
    selected_rounds = median_best_round(rounds, int(config.classifier["n_estimators"]))
    deployment = XGBClassifier(**parameters(config, ratio, rounds=selected_rounds))
    deployment.fit(
        feature_matrix(final_train, feature_columns),
        final_train["y_entry"].astype("int8"),
        sample_weight=final_train["sample_weight"].astype(float),
        verbose=False,
    )

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run = args.output_root / config.model_version / "runs" / run_id
    (run / "predictions").mkdir(parents=True, exist_ok=False)
    (run / "audit").mkdir()
    (run / "model").mkdir()
    oof.to_parquet(run / "predictions/oof_predictions.parquet", index=False)
    pd.DataFrame(raw_fold_rows).merge(
        temporal_audit, on="fold_id", how="left", suffixes=("_raw", "_temporal")
    ).to_csv(run / "audit/fold_metrics.csv", index=False)
    write_json(oof_metrics, run / "audit/oof_metrics.json")
    deployment.save_model(run / "model/classifier.json")
    joblib.dump(deployment, run / "model/classifier.joblib")
    write_json(deployment_calibrator.to_dict(), run / "model/calibration.json")
    write_json({
        "threshold": deployment_threshold,
        "source": "all causal OOF",
    }, run / "model/decision_policy.json")
    write_json({"feature_columns": feature_columns}, run / "model/features.json")
    model_manifest = {
        "model_version": config.model_version,
        "run_id": run_id,
        "dataset_dependency": str(dataset_run),
        "architecture": "XGBClassifier structural-breakdown head",
        "calibration": "prior-fold-only temporal sigmoid OOF",
        "selected_rounds": selected_rounds,
        "deployment_threshold": deployment_threshold,
        "final_test_evaluated": False,
    }
    write_json(model_manifest, run / "model_manifest.json")
    write_json({**model_manifest, "run_directory": str(run.resolve())}, args.output_root / config.model_version / "latest.json")
    print(json.dumps(normalize(oof_metrics), indent=2))
    print(f"Breakdown model run: {run.resolve()}")


if __name__ == "__main__":
    main()
