"""Open and report the H120 final holdout for an already-frozen combiner.

The command cannot train, tune a threshold, or promote a deployment artifact.
It only combines H20/H60/H120 prediction files produced by pinned model runs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.multihorizon_final import (  # noqa: E402
    evaluate_frozen_combiner,
    join_final_predictions,
    load_final_prediction,
)
from src.models.multihorizon import MultiHorizonMetaModel  # noqa: E402

FINAL_TEST_CONFIRMATION = "OPEN_FROZEN_MULTIHORIZON_FINAL_ONCE"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--combiner-run", type=Path, required=True)
    parser.add_argument("--h20-final", type=Path, required=True)
    parser.add_argument("--h60-final", type=Path, required=True)
    parser.add_argument("--h120-final", type=Path, required=True)
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs/experiments/wave_multihorizon_final_v1.yaml",
    )
    parser.add_argument(
        "--confirm-final-test",
        default="",
        help=f"Required exact value: {FINAL_TEST_CONFIRMATION}",
    )
    parser.add_argument(
        "--coverage-policy",
        choices=("intersection", "missing_aware"),
        required=True,
        help="intersection for legacy 3-input artifacts; missing_aware only for MultiHorizonMetaModel.",
    )
    parser.add_argument("--output-root", type=Path, default=ROOT / "eval/runs/multihorizon_final")
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): normalize_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize_json(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    return value


def write_json(payload: dict[str, Any], path: Path) -> None:
    path.write_text(
        json.dumps(normalize_json(payload), ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )


def load_frozen_combiner(run: Path) -> tuple[Any, dict[str, Any], float, str, dict[str, Any]]:
    manifest_path = run / "model_manifest.json"
    model_path = run / "meta_model.joblib"
    if not manifest_path.is_file() or not model_path.is_file():
        raise FileNotFoundError("--combiner-run must contain model_manifest.json and meta_model.joblib.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    threshold = manifest.get("deployment_threshold")
    threshold_source = "combiner_manifest"
    if threshold is None:
        # Compatibility for the first v7 run, whose immutable OOF report had
        # the threshold before that field was added to its manifest.
        metrics_path = run / "audit" / "oof_metrics.json"
        if not metrics_path.is_file():
            raise ValueError("Frozen combiner has neither deployment_threshold nor OOF metrics.")
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        threshold = metrics.get("deployment_threshold_from_causal_oof")
        threshold_source = "combiner_oof_metrics_legacy"
    if threshold is None:
        raise ValueError("Frozen combiner does not contain an OOF-frozen deployment threshold.")
    model = joblib.load(model_path)
    expected_columns = ["p_h20", "p_h60", "p_h120", "missing_p_h20", "missing_p_h60", "missing_p_h120"]
    if isinstance(model, MultiHorizonMetaModel):
        if model.feature_columns != expected_columns:
            raise ValueError(f"Unexpected frozen combiner schema: {model.feature_columns}")
        compatibility = {
            "artifact_format": "MultiHorizonMetaModel",
            "runtime_sklearn_version": sklearn.__version__,
            "missing_horizon_scores_allowed": True,
        }
    elif (
        getattr(model, "n_features_in_", None) == 3
        and list(getattr(model, "feature_names_in_", [])) == ["p_h20", "p_h60", "p_h120"]
        and callable(getattr(model, "predict_proba", None))
    ):
        # Early v7 stored its fitted LogisticRegression directly.  All three
        # final horizons are required below, so this has the same inputs as the
        # original estimator and is safe to report, but not to re-save as v7.
        compatibility = {
            "artifact_format": "legacy_raw_logistic_regression",
            "runtime_sklearn_version": sklearn.__version__,
            "missing_horizon_scores_allowed": False,
            "warning": "Loaded a legacy sklearn pickle; reproduce inference in sklearn 1.7 before promotion.",
        }
    else:
        raise TypeError("Frozen meta_model.joblib has an unsupported combiner schema.")
    return model, manifest, float(threshold), threshold_source, compatibility


def predict_frozen_combiner(model: Any, frame: pd.DataFrame) -> np.ndarray:
    """Apply a supported frozen artifact without fitting or imputing from test rows."""
    if isinstance(model, MultiHorizonMetaModel):
        return model.predict_proba(frame)
    return model.predict_proba(frame[["p_h20", "p_h60", "p_h120"]])[:, 1]


def render_markdown(manifest: dict[str, Any], metrics: dict[str, Any]) -> str:
    combiner = metrics["combiner"]
    baseline = metrics["h120_baseline_same_rows"]
    top_k = metrics["top_k"]
    return "\n".join(
        [
            f"# Multi-horizon final holdout — {manifest['evaluation_id']}",
            "",
            "This is a one-time observation of the H120 final holdout. No model, feature set,",
            "ranker, or threshold was selected from these outcomes; this run does not auto-promote.",
            "",
            "| Metric | Frozen combiner | H120 base model |",
            "|---|---:|---:|",
            f"| ROC-AUC | {combiner['roc_auc']:.6f} | {baseline['roc_auc']:.6f} |",
            f"| PR-AUC | {combiner['average_precision']:.6f} | {baseline['average_precision']:.6f} |",
            f"| Brier score | {combiner['brier_score']:.6f} | {baseline['brier_score']:.6f} |",
            f"| Precision at frozen threshold | {combiner['precision']:.6f} | {baseline['precision']:.6f} |",
            f"| Recall at frozen threshold | {combiner['recall']:.6f} | {baseline['recall']:.6f} |",
            f"| F1 at frozen threshold | {combiner['f1']:.6f} | {baseline['f1']:.6f} |",
            "",
            f"Top-{top_k['k']} daily precision: {top_k['combiner']['event_weighted_precision']:.6f} "
            f"vs {top_k['h120_baseline_same_rows']['event_weighted_precision']:.6f} "
            f"(relative gain {top_k['combiner']['lift_vs_h120_baseline']:.2%}).",
            "",
        ]
    )


def main() -> None:
    args = parse_args()
    if args.confirm_final_test != FINAL_TEST_CONFIRMATION:
        raise RuntimeError(
            "Final holdout remains sealed. Supply "
            f"--confirm-final-test {FINAL_TEST_CONFIRMATION} after OOF selection is frozen."
        )
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    if config.get("final_test_used_for_selection"):
        raise ValueError("The WP6 config must explicitly prohibit final-test model selection.")
    model, combiner_manifest, threshold, threshold_source, compatibility = load_frozen_combiner(args.combiner_run)
    if args.coverage_policy == "missing_aware" and not compatibility["missing_horizon_scores_allowed"]:
        raise ValueError("The legacy raw logistic artifact only supports --coverage-policy intersection.")
    final_paths = {"h20": args.h20_final, "h60": args.h60_final, "h120": args.h120_final}
    frames = {name: load_final_prediction(str(path), name) for name, path in final_paths.items()}
    joined, coverage = join_final_predictions(frames, coverage_policy=args.coverage_policy)
    metrics, predictions = evaluate_frozen_combiner(
        joined,
        probability=predict_frozen_combiner(model, joined),
        threshold=threshold,
        top_k=int(config["ranking"]["top_k"]),
    )
    metrics["coverage"] = coverage
    evaluation_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    final_directory = args.output_root / config["experiment_version"] / evaluation_id
    temporary = final_directory.parent / f".incomplete-{evaluation_id}"
    temporary.mkdir(parents=True, exist_ok=False)
    completed = False
    try:
        report_manifest = {
            "evaluation_id": evaluation_id,
            "experiment_version": config["experiment_version"],
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "status": "final_holdout_observed_not_promoted",
            "final_test_opened": True,
            "retrained": False,
            "threshold_source": threshold_source,
            "artifact_compatibility": compatibility,
            "coverage_policy": args.coverage_policy,
            "frozen_threshold": threshold,
            "combiner_run": str(args.combiner_run.resolve()),
            "combiner_model_sha256": sha256_file(args.combiner_run / "meta_model.joblib"),
            "combiner_manifest_sha256": sha256_file(args.combiner_run / "model_manifest.json"),
            "source_final_prediction_sha256": {name: sha256_file(path) for name, path in final_paths.items()},
            "source_final_prediction_paths": {name: str(path.resolve()) for name, path in final_paths.items()},
            "combiner_oof_inputs": combiner_manifest.get("inputs", {}),
            "auto_promote": False,
        }
        predictions.to_parquet(temporary / "final_test_predictions.parquet", index=False)
        write_json(metrics, temporary / "metrics.json")
        write_json(report_manifest, temporary / "evaluation_manifest.json")
        (temporary / "report.md").write_text(render_markdown(report_manifest, metrics), encoding="utf-8")
        temporary.rename(final_directory)
        write_json(
            {**report_manifest, "evaluation_directory": str(final_directory.resolve())},
            final_directory.parent / "latest.json",
        )
        completed = True
        print(json.dumps(normalize_json(report_manifest), ensure_ascii=False, indent=2))
        print(json.dumps(normalize_json(metrics), ensure_ascii=False, indent=2))
        print(f"Multi-horizon final evaluation: {final_directory.resolve()}")
    finally:
        if not completed and temporary.exists():
            shutil.rmtree(temporary)


if __name__ == "__main__":
    main()
