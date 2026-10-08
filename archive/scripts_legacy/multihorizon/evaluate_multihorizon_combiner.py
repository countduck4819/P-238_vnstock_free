"""Evaluate a causal H20/H60/H120 OOF probability combiner.

This command intentionally consumes only OOF predictions.  It never reads a
final-test table, so the resulting threshold and metrics are safe for model
selection before a new untouched paper-trading period.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    f1_score,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.models.multihorizon import (  # noqa: E402
    causal_meta_oof,
    fit_meta_model,
    load_oof,
    select_f1_threshold,
)

MODEL_ROOTS = {
    "h20": ROOT / "models/wave_ignition/xgboost_wave_v6_trend20",
    "h60": ROOT / "models/wave_ignition/xgboost_continuation_h60",
    "h120": ROOT / "models/wave_ignition/xgboost_continuation_h120",
}


def latest_oof(model_root: Path) -> Path:
    latest_path = model_root / "latest.json"
    if not latest_path.exists():
        raise FileNotFoundError(
            f"No latest model pointer found at {latest_path}; pass an explicit OOF path."
        )
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    run_directory = Path(latest["run_directory"])
    if not run_directory.is_absolute():
        run_directory = ROOT / run_directory
    oof_path = run_directory / "predictions" / "oof_predictions.parquet"
    if not oof_path.exists():
        raise FileNotFoundError(f"Latest model run has no OOF predictions: {oof_path}")
    return oof_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--h20", type=Path)
    parser.add_argument("--h60", type=Path)
    parser.add_argument("--h120", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "models/wave_ignition/multihorizon_v7")
    args = parser.parse_args()
    resolved_inputs = {
        horizon: path if path is not None else latest_oof(MODEL_ROOTS[horizon])
        for horizon, path in {"h20": args.h20, "h60": args.h60, "h120": args.h120}.items()
    }
    frames = {
        horizon: load_oof(str(path), horizon)
        for horizon, path in resolved_inputs.items()
    }
    merged, fold_metrics = causal_meta_oof(frames)
    predictions = merged.loc[merged["p_meta"].notna()].copy()
    classified = predictions.loc[predictions["meta_threshold"].notna()].copy()
    y = predictions["y_entry_h120"].to_numpy(dtype=int)
    probability = predictions["p_meta"].to_numpy(dtype=float)
    weight = predictions["sample_weight_h120"].to_numpy(dtype=float)
    classified_y = classified["y_entry_h120"].to_numpy(dtype=int)
    classified_weight = classified["sample_weight_h120"].to_numpy(dtype=float)
    predicted = classified["p_meta"].to_numpy(dtype=float) >= classified[
        "meta_threshold"
    ].to_numpy(dtype=float)
    deployment_threshold = select_f1_threshold(y, probability, weight)
    h120_probability = predictions["p_h120"].to_numpy(dtype=float)
    metrics = {
        "rows": int(len(predictions)),
        "classification_rows_with_nested_threshold": int(len(classified)),
        "positive_rate": float(np.average(y, weights=weight)),
        "roc_auc": _safe(roc_auc_score, y, probability, weight),
        "average_precision": _safe(average_precision_score, y, probability, weight),
        "brier_score": _safe(brier_score_loss, y, probability, weight),
        "log_loss": _safe(log_loss, y, probability, weight),
        "expected_calibration_error_10": expected_calibration_error(y, probability, weight),
        "precision": float(
            precision_score(classified_y, predicted, sample_weight=classified_weight, zero_division=0)
        ),
        "recall": float(
            recall_score(classified_y, predicted, sample_weight=classified_weight, zero_division=0)
        ),
        "f1": float(f1_score(classified_y, predicted, sample_weight=classified_weight, zero_division=0)),
        "deployment_threshold_from_causal_oof": deployment_threshold,
        "same_rows_h120_baseline": {
            "roc_auc": _safe(roc_auc_score, y, h120_probability, weight),
            "average_precision": _safe(average_precision_score, y, h120_probability, weight),
            "brier_score": _safe(brier_score_loss, y, h120_probability, weight),
        },
        "coverage": {
            column: float(merged[column].notna().mean()) for column in ["p_h20", "p_h60", "p_h120"]
        },
        "folds": sorted(predictions["fold_id"].unique().tolist()),
        "target": "h120_continuation",
        "features": ["p_h20", "p_h60", "p_h120"],
        "note": "OOF-only causal meta evaluation; no final-test data used.",
    }
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = args.output / "runs" / run_id
    (run_dir / "audit").mkdir(parents=True, exist_ok=True)
    (run_dir / "predictions").mkdir(parents=True, exist_ok=True)
    meta_model = fit_meta_model(merged)
    model_path = run_dir / "meta_model.joblib"
    joblib.dump(meta_model, model_path)
    predictions.to_parquet(run_dir / "predictions" / "oof_predictions.parquet", index=False)
    fold_metrics.to_csv(run_dir / "audit" / "fold_metrics.csv", index=False)
    (run_dir / "audit" / "oof_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    manifest = {
        "run_id": run_id,
        "model_type": "causal_logistic_multihorizon",
        "inputs": {key: str(path.resolve()) for key, path in resolved_inputs.items()},
        "feature_columns": meta_model.feature_columns,
        "imputation_values": meta_model.imputation_values,
        "deployment_threshold": deployment_threshold,
        "model_sha256": sha256_file(model_path),
        "metrics": str(run_dir / "audit/oof_metrics.json"),
    }
    (run_dir / "model_manifest.json").write_text(
        json.dumps(manifest, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps({"run_dir": str(run_dir), "metrics": metrics}, indent=2))


def _safe(function, y_true, probability, weight) -> float:
    try:
        return float(function(y_true, probability, sample_weight=weight))
    except ValueError:
        return float("nan")


def expected_calibration_error(
    y_true: np.ndarray, probability: np.ndarray, weight: np.ndarray, bins: int = 10
) -> float:
    edges = np.linspace(0.0, 1.0, bins + 1)
    assignments = np.clip(np.digitize(probability, edges[1:-1]), 0, bins - 1)
    total = float(weight.sum())
    error = 0.0
    for index in range(bins):
        mask = assignments == index
        if not mask.any():
            continue
        bin_weight = float(weight[mask].sum())
        observed = float(np.average(y_true[mask], weights=weight[mask]))
        predicted = float(np.average(probability[mask], weights=weight[mask]))
        error += bin_weight / total * abs(observed - predicted)
    return float(error)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
