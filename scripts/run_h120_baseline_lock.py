"""Freeze and reproduce the E00 H120 baseline from immutable OOF artifacts.

The command is deliberately read-only with respect to frozen model artifacts.  It
writes only the Phase-0 registry, lock, and reports under the requested output
paths.  A run fails if the reproduced metrics do not match the source audits.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


UPSTREAM_RUN = Path(
    "models/wave_ignition_snapshot/xgboost_continuation_h120/runs/20260823T052814Z"
)
CASCADE_RUN = Path(
    "models/wave_ignition_snapshot/wave_cascade_research_v4_h120_only/runs/20260823T170819Z"
)
CASCADE_CONFIG = Path("configs/experiments/wave_cascade_v4_h120_only.yaml")
SOURCE_LOCK = Path("experiments/baselines/wave_cascade_research_v4_h120_only_lock.json")
SHADOW_BUNDLE = Path("deploy/wave_h120_shadow/bundle_manifest.json")
FINAL_TEST_MANIFEST = Path("eval/runs/wave_cascade_prod_v3_final_test/manifest.json")

DEFAULT_LOCK = Path("experiments/h120_improvement/baseline_lock.json")
DEFAULT_REGISTRY = Path("experiments/h120_improvement/registry.json")
DEFAULT_REPORT_ROOT = Path("reports/h120_improvement/E00_baseline")

METRIC_TOLERANCE = 1e-12


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_path(path: Path) -> str:
    return path.resolve().relative_to(PROJECT_ROOT).as_posix()


def file_record(path: Path, role: str) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Required baseline artifact is missing: {resolved}")
    return {
        "role": role,
        "path": relative_path(resolved),
        "size_bytes": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
    }


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def git_info() -> dict[str, Any]:
    def run(*args: str) -> str | None:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=PROJECT_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError):
            return None
        return result.stdout.strip()

    status = run("status", "--short", "--untracked-files=all")
    return {
        "commit": run("rev-parse", "HEAD"),
        "status_clean": status == "",
        "status_short": status.splitlines() if status else [],
    }


def _finite_metric_rows(
    frame: pd.DataFrame,
    probability_column: str,
    target_column: str,
) -> pd.DataFrame:
    required = {"fold_id", "date", "symbol", probability_column, target_column, "sample_weight"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Baseline frame is missing columns: {missing}")
    result = frame.copy()
    result[probability_column] = pd.to_numeric(result[probability_column], errors="coerce")
    result["sample_weight"] = pd.to_numeric(result["sample_weight"], errors="coerce")
    result[target_column] = pd.to_numeric(result[target_column], errors="coerce")
    return result.loc[
        result[probability_column].notna()
        & result["sample_weight"].notna()
        & result[target_column].notna()
    ].copy()


def daily_top10_rows(
    frame: pd.DataFrame,
    *,
    surface: str,
    probability_column: str,
    target_column: str,
    k: int = 10,
) -> pd.DataFrame:
    """Return one deterministic Top-10 record per date for a baseline surface."""

    if k <= 0:
        raise ValueError("k must be positive.")
    scored = _finite_metric_rows(frame, probability_column, target_column)
    records: list[dict[str, Any]] = []
    ordered = scored.sort_values(
        ["date", probability_column, "symbol"],
        ascending=[True, False, True],
        kind="stable",
    )
    for date, group in ordered.groupby("date", observed=True, sort=False):
        selected = group.head(k)
        selected_weight = selected["sample_weight"].to_numpy(dtype=float)
        selected_target = selected[target_column].to_numpy(dtype=float)
        universe_weight = group["sample_weight"].to_numpy(dtype=float)
        universe_target = group[target_column].to_numpy(dtype=float)
        precision = float(np.average(selected_target, weights=selected_weight))
        base_rate = float(np.average(universe_target, weights=universe_weight))
        records.append(
            {
                "surface": surface,
                "fold_id": str(group["fold_id"].iloc[0]),
                "date": pd.Timestamp(date),
                "universe_rows": int(len(group)),
                "selected_rows": int(len(selected)),
                "selected_positive_rate": precision,
                "universe_positive_rate": base_rate,
                "lift": precision / base_rate if base_rate > 0 else math.nan,
                "top_score": float(selected[probability_column].iloc[0]),
                "cutoff_score": float(selected[probability_column].iloc[-1]),
            }
        )
    return pd.DataFrame(records)


def _daily_top10_summary(daily: pd.DataFrame) -> dict[str, float]:
    if daily.empty:
        return {
            "days": 0.0,
            "daily_precision_at_10_mean": math.nan,
            "daily_precision_at_10_median": math.nan,
            "daily_base_rate_mean": math.nan,
            "daily_lift_at_10_mean": math.nan,
            "daily_lift_at_10_min": math.nan,
        }
    return {
        "days": float(len(daily)),
        "daily_precision_at_10_mean": float(daily["selected_positive_rate"].mean()),
        "daily_precision_at_10_median": float(daily["selected_positive_rate"].median()),
        "daily_base_rate_mean": float(daily["universe_positive_rate"].mean()),
        "daily_lift_at_10_mean": float(daily["lift"].mean()),
        "daily_lift_at_10_min": float(daily["lift"].min()),
    }


def surface_metrics(
    frame: pd.DataFrame,
    *,
    surface: str,
    probability_column: str,
    target_column: str,
    threshold: float,
) -> tuple[dict[str, Any], pd.DataFrame]:
    """Evaluate a single OOF surface and its exact per-date Top-10 rows."""

    from src.evaluation.wave_cascade import cascade_metrics

    metrics = cascade_metrics(
        frame,
        probability_column=probability_column,
        target_column=target_column,
        threshold=threshold,
        top_k=10,
    )
    daily = daily_top10_rows(
        frame,
        surface=surface,
        probability_column=probability_column,
        target_column=target_column,
        k=10,
    )
    metrics["surface"] = surface
    metrics["probability_column"] = probability_column
    metrics["daily_top10"] = _daily_top10_summary(daily)
    return metrics, daily


def fold_metrics(
    frame: pd.DataFrame,
    *,
    surface: str,
    probability_column: str,
    target_column: str,
    default_threshold: float,
    threshold_column: str | None = None,
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for fold_id, group in frame.groupby("fold_id", observed=True, sort=True):
        if _finite_metric_rows(group, probability_column, target_column).empty:
            continue
        if threshold_column and threshold_column in group:
            thresholds = pd.to_numeric(group[threshold_column], errors="coerce").dropna().unique()
            threshold = float(thresholds[0]) if len(thresholds) == 1 else math.inf
            threshold_available = len(thresholds) == 1
        else:
            threshold = default_threshold
            threshold_available = True
        metrics, _ = surface_metrics(
            group,
            surface=surface,
            probability_column=probability_column,
            target_column=target_column,
            threshold=threshold,
        )
        top_k = metrics["top_k"]
        records.append(
            {
                "surface": surface,
                "fold_id": str(fold_id),
                "rows": int(metrics["rows"]),
                "days": int(metrics["days"]),
                "positive_rate": metrics["positive_rate"],
                "roc_auc": metrics["roc_auc"],
                "average_precision": metrics["average_precision"],
                "brier_score": metrics["brier_score"],
                "threshold": threshold if threshold_available else math.nan,
                "precision": metrics["precision"] if threshold_available else math.nan,
                "recall": metrics["recall"] if threshold_available else math.nan,
                "f1": metrics["f1"] if threshold_available else math.nan,
                "daily_precision_at_10_mean": metrics["daily_top10"]["daily_precision_at_10_mean"],
                "daily_lift_at_10_mean": metrics["daily_top10"]["daily_lift_at_10_mean"],
                "event_weighted_precision_at_10": top_k["event_weighted_precision"],
                "event_weighted_lift_at_10": top_k["lift"],
            }
        )
    return pd.DataFrame(records)


def calibration_by_fold(
    frame: pd.DataFrame,
    *,
    surface: str,
    probability_column: str,
    target_column: str,
) -> pd.DataFrame:
    from src.evaluation.wave_model import (
        calibration_diagnostics,
        calibration_slope_intercept,
        calibration_table,
    )

    records: list[dict[str, Any]] = []
    for fold_id, group in frame.groupby("fold_id", observed=True, sort=True):
        scored = _finite_metric_rows(group, probability_column, target_column)
        if scored.empty or scored[target_column].nunique() < 2:
            continue
        renamed = scored.rename(columns={probability_column: "probability", target_column: "y_entry"})
        weights = renamed["sample_weight"].to_numpy(dtype=float)
        labels = renamed["y_entry"].to_numpy(dtype=int)
        probabilities = renamed["probability"].to_numpy(dtype=float)
        table = calibration_table(renamed, probability_column="probability", bins=10)
        diagnostics = calibration_diagnostics(table)
        slope = calibration_slope_intercept(renamed, probability_column="probability")
        records.append(
            {
                "surface": surface,
                "fold_id": str(fold_id),
                "rows": int(len(renamed)),
                "days": int(renamed["date"].nunique()),
                "positive_rate": float(np.average(labels, weights=weights)),
                "mean_prediction": float(np.average(probabilities, weights=weights)),
                "mean_prediction_minus_actual": float(
                    np.average(probabilities, weights=weights) - np.average(labels, weights=weights)
                ),
                "average_precision": float(average_precision_score(labels, probabilities, sample_weight=weights)),
                "roc_auc": float(roc_auc_score(labels, probabilities, sample_weight=weights)),
                "brier_score": float(brier_score_loss(labels, probabilities, sample_weight=weights)),
                **diagnostics,
                **slope,
            }
        )
    return pd.DataFrame(records)


def _assert_close(actual: float, expected: float, label: str) -> None:
    if not math.isclose(float(actual), float(expected), rel_tol=0.0, abs_tol=METRIC_TOLERANCE):
        raise RuntimeError(
            f"Baseline metric mismatch for {label}: actual={actual}, expected={expected}, "
            f"tolerance={METRIC_TOLERANCE}"
        )


def assert_source_reconciliation(
    metrics: dict[str, dict[str, Any]],
    cascade_audit: dict[str, Any],
    upstream_audit: dict[str, Any],
) -> None:
    checks = (
        (
            "cascade_raw_causal_oof",
            cascade_audit,
            ("rows", "days", "positive_rate", "roc_auc", "average_precision", "brier_score", "precision", "recall", "f1"),
        ),
        (
            "cascade_temporal_calibrated_oof",
            cascade_audit["calibrated_oof"],
            ("rows", "days", "positive_rate", "roc_auc", "average_precision", "brier_score", "precision", "recall", "f1"),
        ),
        (
            "upstream_raw_oof",
            upstream_audit["raw_oof_at_0_5"],
            ("rows", "positive_rate", "roc_auc", "average_precision", "brier_score", "precision", "recall", "f1"),
        ),
        (
            "upstream_temporal_calibration_audit_fold_2024",
            upstream_audit["temporal_calibration_audit"]["metrics"],
            ("rows", "positive_rate", "roc_auc", "average_precision", "brier_score", "precision", "recall", "f1"),
        ),
    )
    for surface, reference, keys in checks:
        actual = metrics[surface]
        for key in keys:
            _assert_close(actual[key], reference[key], f"{surface}.{key}")

    top_k_checks = (
        ("cascade_raw_causal_oof", cascade_audit["top_k"]),
        ("cascade_temporal_calibrated_oof", cascade_audit["calibrated_oof"]["top_k"]),
    )
    for surface, reference in top_k_checks:
        actual_top_k = metrics[surface]["top_k"]
        for key in ("selected_rows", "selected_days", "event_weighted_precision", "base_rate", "lift"):
            _assert_close(actual_top_k[key], reference[key], f"{surface}.top_k.{key}")


def load_and_validate_contracts(
    *,
    upstream_run: Path,
    cascade_run: Path,
    cascade_config: Path,
    shadow_bundle: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    upstream_manifest = read_json(upstream_run / "model_manifest.json")
    cascade_manifest = read_json(cascade_run / "model_manifest.json")
    bundle_manifest = read_json(shadow_bundle)
    config = yaml.safe_load(cascade_config.read_text(encoding="utf-8"))
    if upstream_manifest.get("model_version") != "xgboost_continuation_h120":
        raise RuntimeError("Baseline upstream run is not continuation H120.")
    if upstream_manifest.get("final_test_evaluated"):
        raise RuntimeError("Baseline upstream run must not have opened its final test.")
    if cascade_manifest.get("experiment_version") != "wave_cascade_v4_h120_only":
        raise RuntimeError("Baseline cascade run is not the H120-only v4 experiment.")
    if cascade_manifest.get("final_test_used_for_selection") is not False:
        raise RuntimeError("Baseline cascade unexpectedly used the final test for selection.")
    if config.get("final_test_used_for_selection") is not False:
        raise RuntimeError("H120 improvement config must set final_test_used_for_selection=false.")
    if config.get("features", {}).get("probability_columns") != ["p_h120"]:
        raise RuntimeError("H120 baseline must retain the p_h120-only cascade contract.")
    if bundle_manifest.get("deployment_status") != "shadow_candidate_requires_new_holdout":
        raise RuntimeError("Baseline deployment status is not the expected shadow state.")
    if bundle_manifest.get("contract", {}).get("trade_authorized") is not False:
        raise RuntimeError("Baseline bundle must remain trade_authorized=false.")
    return upstream_manifest, cascade_manifest, bundle_manifest, config


def evaluate_baseline(
    *,
    upstream_run: Path = UPSTREAM_RUN,
    cascade_run: Path = CASCADE_RUN,
) -> tuple[dict[str, dict[str, Any]], pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Recompute all Phase-0 metric surfaces without writing any files."""

    cascade_manifest = read_json(cascade_run / "model_manifest.json")
    upstream_audit = read_json(upstream_run / "audit/oof_metrics.json")
    cascade_audit = read_json(cascade_run / "audit/metrics.json")

    upstream = pd.read_parquet(upstream_run / "predictions/oof_predictions.parquet").rename(
        columns={"y_entry": "y_cont_h120"}
    )
    cascade = pd.read_parquet(cascade_run / "predictions/oof_predictions.parquet")

    surfaces: list[tuple[str, pd.DataFrame, str, float]] = [
        ("upstream_raw_oof", upstream, "p_entry_raw", 0.5),
        (
            "upstream_temporal_calibration_audit_fold_2024",
            upstream.loc[
                upstream["fold_id"].eq(
                    upstream_audit["temporal_calibration_audit"]["audit_fold"]
                )
            ].copy(),
            "p_entry_calibrated_temporal",
            float(upstream_audit["temporal_calibration_audit"]["threshold_selected_without_audit_fold"]),
        ),
        (
            "cascade_raw_causal_oof",
            cascade,
            "p_cascade",
            float(cascade_manifest["threshold_from_last_causal_fold"]),
        ),
        (
            "cascade_temporal_calibrated_oof",
            cascade.loc[cascade["cascade_calibration_is_temporal"]].copy(),
            "p_cascade_calibrated",
            float(cascade_manifest["threshold_calibrated"]),
        ),
    ]

    metrics: dict[str, dict[str, Any]] = {}
    daily_frames: list[pd.DataFrame] = []
    fold_frames: list[pd.DataFrame] = []
    calibration_frames: list[pd.DataFrame] = []
    for surface, frame, probability_column, threshold in surfaces:
        surface_result, daily = surface_metrics(
            frame,
            surface=surface,
            probability_column=probability_column,
            target_column="y_cont_h120",
            threshold=threshold,
        )
        metrics[surface] = surface_result
        daily_frames.append(daily)
        threshold_column = None
        if surface == "cascade_raw_causal_oof":
            threshold_column = "cascade_threshold"
        elif surface == "cascade_temporal_calibrated_oof":
            threshold_column = "cascade_calibrated_threshold"
        fold_frames.append(
            fold_metrics(
                frame,
                surface=surface,
                probability_column=probability_column,
                target_column="y_cont_h120",
                default_threshold=threshold,
                threshold_column=threshold_column,
            )
        )
        calibration_frames.append(
            calibration_by_fold(
                frame,
                surface=surface,
                probability_column=probability_column,
                target_column="y_cont_h120",
            )
        )

    assert_source_reconciliation(metrics, cascade_audit, upstream_audit)
    return (
        metrics,
        pd.concat(daily_frames, ignore_index=True),
        pd.concat(fold_frames, ignore_index=True),
        pd.concat(calibration_frames, ignore_index=True),
    )


def baseline_lock_payload(
    *,
    upstream_run: Path,
    cascade_run: Path,
    cascade_config: Path,
    source_lock: Path,
    shadow_bundle: Path,
    final_test_manifest: Path,
    metrics: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    upstream_manifest, cascade_manifest, bundle_manifest, _ = load_and_validate_contracts(
        upstream_run=upstream_run,
        cascade_run=cascade_run,
        cascade_config=cascade_config,
        shadow_bundle=shadow_bundle,
    )
    records = [
        file_record(upstream_run / "model_manifest.json", "upstream_manifest"),
        file_record(upstream_run / "model/features.json", "upstream_feature_schema"),
        file_record(upstream_run / "predictions/oof_predictions.parquet", "upstream_oof_predictions"),
        file_record(upstream_run / "audit/oof_metrics.json", "upstream_oof_metrics"),
        file_record(upstream_run / "audit/fold_metrics.csv", "upstream_fold_metrics"),
        file_record(cascade_run / "model_manifest.json", "cascade_manifest"),
        file_record(cascade_run / "model/meta_model.joblib", "cascade_meta_model"),
        file_record(cascade_run / "model/calibration.json", "cascade_calibration"),
        file_record(cascade_run / "predictions/oof_predictions.parquet", "cascade_oof_predictions"),
        file_record(cascade_run / "audit/metrics.json", "cascade_oof_metrics"),
        file_record(cascade_run / "audit/fold_metrics.csv", "cascade_fold_metrics"),
        file_record(cascade_config, "cascade_experiment_config"),
        file_record(source_lock, "preexisting_cascade_lock"),
        file_record(shadow_bundle, "shadow_bundle_manifest"),
        file_record(final_test_manifest, "contaminated_final_test_manifest"),
    ]
    return {
        "schema_version": 1,
        "baseline_id": "h120_shadow_champion_e00_20260824",
        "phase": "E00_baseline",
        "status": "frozen_shadow_champion_reproduced",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "selection_scope": "causal_oof_only",
        "final_test_used_for_selection": False,
        "champion": {
            "upstream_model_version": upstream_manifest["model_version"],
            "upstream_run_id": upstream_manifest["run_id"],
            "cascade_version": cascade_manifest["experiment_version"],
            "cascade_run_id": cascade_manifest["run_id"],
            "ranking_column": bundle_manifest["contract"]["ranking_column"],
            "shortlist_k": bundle_manifest["contract"]["shortlist_k"],
            "trade_authorized": bundle_manifest["contract"]["trade_authorized"],
            "deployment_status": bundle_manifest["deployment_status"],
        },
        "final_test_policy": {
            "path": relative_path(final_test_manifest),
            "status": "contaminated_postmortem_only",
            "selection_allowed": False,
            "reason": "Final test v3 was already opened before the H120 improvement program.",
        },
        "metric_tolerance": METRIC_TOLERANCE,
        "reproduced_metric_surfaces": metrics,
        "files": records,
        "git": git_info(),
    }


def registry_payload(lock_path: Path, report_root: Path) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "program": "h120_improvement",
        "selection_scope": "causal_oof_only",
        "final_test_policy": "contaminated_postmortem_only",
        "experiments": [
            {
                "experiment_id": "E00_baseline",
                "status": "completed",
                "baseline_id": "h120_shadow_champion_e00_20260824",
                "lock": relative_path(lock_path),
                "report_root": relative_path(report_root),
                "next_checkpoint": "E01_correct_daily_top10_evaluator",
                "final_test_used_for_selection": False,
            }
        ],
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _ensure_writable_targets(paths: list[Path], overwrite: bool) -> None:
    existing = [path for path in paths if path.exists()]
    if existing and not overwrite:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Refusing to overwrite baseline output(s): {joined}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream-run", type=Path, default=UPSTREAM_RUN)
    parser.add_argument("--cascade-run", type=Path, default=CASCADE_RUN)
    parser.add_argument("--cascade-config", type=Path, default=CASCADE_CONFIG)
    parser.add_argument("--source-lock", type=Path, default=SOURCE_LOCK)
    parser.add_argument("--shadow-bundle", type=Path, default=SHADOW_BUNDLE)
    parser.add_argument("--final-test-manifest", type=Path, default=FINAL_TEST_MANIFEST)
    parser.add_argument("--lock-output", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--registry-output", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--report-root", type=Path, default=DEFAULT_REPORT_ROOT)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    upstream_run = args.upstream_run.resolve()
    cascade_run = args.cascade_run.resolve()
    cascade_config = args.cascade_config.resolve()
    source_lock = args.source_lock.resolve()
    shadow_bundle = args.shadow_bundle.resolve()
    final_test_manifest = args.final_test_manifest.resolve()
    lock_output = args.lock_output.resolve()
    registry_output = args.registry_output.resolve()
    report_root = args.report_root.resolve()
    report_files = [
        report_root / "metrics.json",
        report_root / "fold_metrics.csv",
        report_root / "daily_top10.csv",
        report_root / "calibration_by_fold.csv",
    ]
    _ensure_writable_targets([lock_output, registry_output, *report_files], args.overwrite)

    load_and_validate_contracts(
        upstream_run=upstream_run,
        cascade_run=cascade_run,
        cascade_config=cascade_config,
        shadow_bundle=shadow_bundle,
    )
    metrics, daily, folds, calibration = evaluate_baseline(
        upstream_run=upstream_run,
        cascade_run=cascade_run,
    )
    lock = baseline_lock_payload(
        upstream_run=upstream_run,
        cascade_run=cascade_run,
        cascade_config=cascade_config,
        source_lock=source_lock,
        shadow_bundle=shadow_bundle,
        final_test_manifest=final_test_manifest,
        metrics=metrics,
    )
    report_root.mkdir(parents=True, exist_ok=True)
    _write_json(report_root / "metrics.json", {"schema_version": 1, "surfaces": metrics})
    folds.to_csv(report_root / "fold_metrics.csv", index=False)
    daily.to_csv(report_root / "daily_top10.csv", index=False, date_format="%Y-%m-%d")
    calibration.to_csv(report_root / "calibration_by_fold.csv", index=False)
    _write_json(lock_output, lock)
    _write_json(registry_output, registry_payload(lock_output, report_root))
    print(
        json.dumps(
            {
                "status": "phase_0_complete",
                "baseline_id": lock["baseline_id"],
                "lock": relative_path(lock_output),
                "registry": relative_path(registry_output),
                "report_root": relative_path(report_root),
                "primary_surface": "cascade_temporal_calibrated_oof",
                "primary_daily_precision_at_10": metrics[
                    "cascade_temporal_calibrated_oof"
                ]["daily_top10"]["daily_precision_at_10_mean"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
