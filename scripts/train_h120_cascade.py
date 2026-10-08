"""Train the causal H120 cascade meta-model from a joined OOF table."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.wave_cascade import (  # noqa: E402
    add_strength_ranking_score,
    cascade_metrics,
    daily_candidate_pool_mask,
)
from src.models.wave_cascade import (  # noqa: E402
    causal_cascade_oof,
    fit_cascade_calibration,
    fit_cascade_model,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frame", type=Path, required=True)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("models/wave_ignition_snapshot/wave_cascade_research_v4_h120_only"),
    )
    parser.add_argument("--experiment-version", default="wave_cascade_v4_h120_only")
    parser.add_argument(
        "--probability-columns",
        default="p_h120",
        help=(
            "Active production candidate: H120 continuation only. V6 remains a "
            "shadow signal and breakdown probabilities are offline-only."
        ),
    )
    parser.add_argument("--continuous-columns", default="")
    parser.add_argument("--target-column", default="y_cont_h120")
    parser.add_argument("--c-value", type=float, default=1.0)
    parser.add_argument(
        "--meta-model",
        choices=("logistic", "hist_gradient_boosting"),
        default="logistic",
        help="Causal fusion estimator used for the cascade ablation.",
    )
    parser.add_argument(
        "--positive-class-weight",
        type=float,
        default=1.0,
        help="Additional sample-weight multiplier for resolved positive targets.",
    )
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--top-k-grid", default="5,10,20,50")
    parser.add_argument("--candidate-column", default="p_h120")
    parser.add_argument("--candidate-k", type=int, default=50)
    parser.add_argument(
        "--candidate-mode",
        choices=("universe", "pool"),
        default="universe",
        help="Production ranking universe; pool retains the legacy hard-gate diagnostic.",
    )
    parser.add_argument("--candidate-k-grid", default="50,100,200")
    parser.add_argument("--strength-columns", default="strength_h120")
    parser.add_argument(
        "--strength-weight",
        type=float,
        default=0.0,
        help="Research-only post-ranking adjustment; production default is disabled.",
    )
    return parser.parse_args()


def existing_columns(frame: pd.DataFrame, value: str) -> tuple[str, ...]:
    return tuple(
        column.strip()
        for column in value.split(",")
        if column.strip()
        and column.strip() in frame.columns
        and frame[column.strip()].notna().any()
    )


def normalize(value):
    if isinstance(value, dict):
        return {str(k): normalize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def parse_int_list(value: str) -> tuple[int, ...]:
    values = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    if not values or any(item <= 0 for item in values):
        raise ValueError("integer grids must contain positive integers.")
    return values


def top_k_comparison(
    frame: pd.DataFrame,
    *,
    probability_column: str,
    threshold: float,
    candidate_column: str | None,
    candidate_k: int,
    top_k_grid: tuple[int, ...],
    strength_columns: tuple[str, ...],
    strength_weight: float,
) -> dict[str, object]:
    ranked = add_strength_ranking_score(
        frame,
        probability_column=probability_column,
        strength_columns=strength_columns,
        strength_weight=strength_weight,
    )
    raw: dict[str, object] = {}
    adjusted: dict[str, object] = {}
    for top_k in top_k_grid:
        candidate_kwargs = (
            {
                "candidate_probability_column": candidate_column,
                "candidate_k": candidate_k,
            }
            if candidate_column is not None
            else {}
        )
        raw_metrics = cascade_metrics(
            frame,
            probability_column=probability_column,
            threshold=threshold,
            top_k=top_k,
            ranking_probability_column=probability_column,
            **candidate_kwargs,
        )
        adjusted_metrics = cascade_metrics(
            ranked,
            probability_column=probability_column,
            threshold=threshold,
            top_k=top_k,
            ranking_probability_column="p_rank",
            **candidate_kwargs,
        )
        raw[str(top_k)] = {
            "top_k": raw_metrics["top_k"],
            "candidate_pool": raw_metrics.get("candidate_pool"),
        }
        adjusted[str(top_k)] = {
            "top_k": adjusted_metrics["top_k"],
            "candidate_pool": adjusted_metrics.get("candidate_pool"),
        }
    return {
        "probability_column": probability_column,
        "strength_columns": list(strength_columns),
        "strength_weight": strength_weight,
        "raw": raw,
        "strength_adjusted": adjusted,
    }


def candidate_policy_comparison(
    frame: pd.DataFrame,
    *,
    candidate_columns: tuple[str, ...],
    candidate_k_grid: tuple[int, ...],
    target_column: str,
    weight_column: str,
) -> dict[str, object]:
    resolved = frame[target_column].notna() & frame[weight_column].notna()
    total_positive = float(
        np.sum(
            frame.loc[resolved, target_column].to_numpy(float)
            * frame.loc[resolved, weight_column].to_numpy(float)
        )
    )
    result: dict[str, object] = {}
    for column in candidate_columns:
        if column not in frame or not frame[column].notna().any():
            continue
        by_k: dict[str, object] = {}
        for candidate_k in candidate_k_grid:
            mask = daily_candidate_pool_mask(frame, column, candidate_k)
            pool = frame.loc[mask]
            pool_resolved = pool[target_column].notna() & pool[weight_column].notna()
            pool_positive = float(
                np.sum(
                    pool.loc[pool_resolved, target_column].to_numpy(float)
                    * pool.loc[pool_resolved, weight_column].to_numpy(float)
                )
            )
            pool_resolved_weight = float(pool.loc[pool_resolved, weight_column].sum())
            by_k[str(candidate_k)] = {
                "candidate_k": candidate_k,
                "candidate_rows": int(len(pool)),
                "candidate_days": int(pool["date"].nunique()),
                "candidate_fraction": float(len(pool) / len(frame)) if len(frame) else np.nan,
                "candidate_positive_rate": float(
                    pool_positive / pool_resolved_weight
                )
                if pool_resolved_weight
                else np.nan,
                "candidate_recall": float(pool_positive / total_positive)
                if total_positive
                else np.nan,
                "candidate_resolved_rows": int(pool_resolved.sum()),
                "candidate_unknown_rows": int((~pool_resolved).sum()),
                "candidate_unknown_rate": float((~pool_resolved).mean()) if len(pool) else np.nan,
            }
        result[column] = {"candidate_k_grid": list(candidate_k_grid), "by_k": by_k}
    return result


def main() -> None:
    args = parse_args()
    frame = pd.read_parquet(args.frame)
    probability_columns = existing_columns(frame, args.probability_columns)
    continuous_columns = existing_columns(frame, args.continuous_columns)
    top_k_grid = parse_int_list(args.top_k_grid)
    candidate_k_grid = parse_int_list(args.candidate_k_grid)
    strength_columns = tuple(
        column.strip() for column in args.strength_columns.split(",") if column.strip()
    )
    if not probability_columns:
        raise ValueError("No requested probability columns are present in the cascade frame.")
    if args.target_column not in frame or "sample_weight" not in frame:
        raise ValueError("Cascade frame must contain target and sample_weight.")
    unresolved = int(frame[args.target_column].isna().sum())
    resolved_frame = frame.loc[frame[args.target_column].notna()].copy()
    if resolved_frame.empty or resolved_frame[args.target_column].nunique() < 2:
        raise ValueError("Cascade frame has insufficient resolved target classes.")
    oof, fold_metrics = causal_cascade_oof(
        frame,
        target_column=args.target_column,
        probability_columns=probability_columns,
        continuous_columns=continuous_columns,
        c_value=args.c_value,
        model_kind=args.meta_model,
        positive_class_weight=args.positive_class_weight,
    )
    valid = oof["p_cascade"].notna()
    if not valid.any():
        raise RuntimeError("No causal cascade folds produced predictions.")
    threshold = float(oof.loc[valid, "cascade_threshold"].dropna().iloc[-1])
    candidate_probability_column = (
        args.candidate_column if args.candidate_mode == "pool" else None
    )
    raw_metrics = cascade_metrics(
        oof.loc[valid],
        target_column=args.target_column,
        threshold=threshold,
        top_k=args.top_k,
        candidate_probability_column=candidate_probability_column,
        candidate_k=args.candidate_k,
    )
    calibrated_valid = oof["p_cascade_calibrated"].notna() & oof[
        "cascade_calibration_is_temporal"
    ]
    calibrated_thresholds = oof.loc[
        calibrated_valid & oof["cascade_calibrated_threshold"].notna(),
        "cascade_calibrated_threshold",
    ]
    if calibrated_thresholds.empty:
        raise RuntimeError("No temporal cascade calibration threshold was produced.")
    calibrated_threshold = float(calibrated_thresholds.iloc[-1])
    calibrated_frame = oof.loc[calibrated_valid].copy()
    calibrated_metrics = cascade_metrics(
        calibrated_frame,
        probability_column="p_cascade_calibrated",
        target_column=args.target_column,
        threshold=calibrated_threshold,
        top_k=args.top_k,
        candidate_probability_column=candidate_probability_column,
        candidate_k=args.candidate_k,
        ranking_probability_column="p_cascade_calibrated",
    )
    audit_candidates = oof.loc[
        oof["cascade_calibrated_threshold"].notna()
        & oof["cascade_calibration_is_temporal"]
    ]
    audit_fold = str(audit_candidates["fold_id"].iloc[-1])
    audit_frame = audit_candidates.loc[audit_candidates["fold_id"].astype(str).eq(audit_fold)]
    temporal_audit = cascade_metrics(
        audit_frame,
        probability_column="p_cascade_calibrated",
        target_column=args.target_column,
        threshold=calibrated_threshold,
        top_k=args.top_k,
        candidate_probability_column=candidate_probability_column,
        candidate_k=args.candidate_k,
        ranking_probability_column="p_cascade_calibrated",
    )
    top_k_metrics = top_k_comparison(
        calibrated_frame,
        probability_column="p_cascade_calibrated",
        threshold=calibrated_threshold,
        candidate_column=candidate_probability_column,
        candidate_k=args.candidate_k,
        top_k_grid=top_k_grid,
        strength_columns=strength_columns,
        strength_weight=args.strength_weight,
    )
    candidate_policies = candidate_policy_comparison(
        calibrated_frame,
        candidate_columns=(
            args.candidate_column,
            "p_h60",
            "p_h120",
            "p_v6_trend",
            "p_cascade_calibrated",
        ),
        candidate_k_grid=candidate_k_grid,
        target_column=args.target_column,
        weight_column="sample_weight",
    )
    top_k_metrics["candidate_policy_comparison"] = candidate_policies
    calibration = fit_cascade_calibration(
        oof.loc[valid],
        probability_column="p_cascade",
        target_column=args.target_column,
        weight_column="sample_weight",
    )
    metrics = {
        **raw_metrics,
        "calibrated_oof": calibrated_metrics,
        "temporal_calibration_audit": {
            "audit_fold": audit_fold,
            **temporal_audit,
        },
        "top_k_comparison": top_k_metrics,
    }
    deployment = fit_cascade_model(
        resolved_frame,
        target_column=args.target_column,
        probability_columns=probability_columns,
        continuous_columns=continuous_columns,
        c_value=args.c_value,
        model_kind=args.meta_model,
        positive_class_weight=args.positive_class_weight,
    )
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = args.output_root / "runs" / run_id
    (run_dir / "predictions").mkdir(parents=True, exist_ok=False)
    (run_dir / "audit").mkdir()
    (run_dir / "model").mkdir()
    oof.to_parquet(run_dir / "predictions/oof_predictions.parquet", index=False)
    fold_metrics.to_csv(run_dir / "audit/fold_metrics.csv", index=False)
    (run_dir / "audit/metrics.json").write_text(
        json.dumps(normalize(metrics), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    joblib.dump(deployment, run_dir / "model/meta_model.joblib")
    calibration_payload = calibration.to_dict()
    calibration_payload.update(
        {
            "input_probability_column": "p_cascade",
            "output_probability_column": "p_cascade_calibrated",
            "fit_rows": int(
                oof.loc[valid, ["p_cascade", args.target_column, "sample_weight"]]
                .notna()
                .all(axis=1)
                .sum()
            ),
            "source_oof": str(args.frame.resolve()),
            "temporal_audit_fold": audit_fold,
            "temporal_audit_threshold": calibrated_threshold,
        }
    )
    (run_dir / "model/calibration.json").write_text(
        json.dumps(normalize(calibration_payload), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    manifest = {
        "run_id": run_id,
        "experiment_version": args.experiment_version,
        "status": "causal_oof_fitted_calibration_audited",
        "selection_scope": "causal_oof_only",
        "final_test_used_for_selection": False,
        "target_column": args.target_column,
        "head_contract": list(probability_columns),
        "probability_columns": list(probability_columns),
        "continuous_columns": list(continuous_columns),
        "meta_model": args.meta_model,
        "positive_class_weight": args.positive_class_weight,
        "threshold_from_last_causal_fold": threshold,
        "threshold_calibrated": calibrated_threshold,
        "source_frame": str(args.frame.resolve()),
        "calibration_artifact": str((run_dir / "model/calibration.json").resolve()),
        "calibration": calibration_payload,
        "warning": (
            "This run is still a causal OOF diagnostic. The sigmoid calibration "
            "is fit from causal OOF predictions, but promotion also requires "
            "Top-K/strength review, final holdout and cost-aware backtest."
        ),
        "candidate_policy": {
            "candidate_column": args.candidate_column,
            "candidate_k": args.candidate_k,
            "candidate_k_grid": list(candidate_k_grid),
            "mode": args.candidate_mode,
            "hard_gate_enabled": args.candidate_mode == "pool",
            "shortlist_k": args.top_k,
            "top_k_grid": list(top_k_grid),
            "strength_columns": list(strength_columns),
            "strength_weight": args.strength_weight,
        },
        "unresolved_target_rows": unresolved,
    }
    (run_dir / "model_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    latest = args.output_root / "latest.json"
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(json.dumps({**manifest, "run_directory": str(run_dir.resolve())}, indent=2), encoding="utf-8")
    print(json.dumps(normalize(metrics), indent=2, ensure_ascii=False))
    print(f"Cascade run: {run_dir.resolve()}")


if __name__ == "__main__":
    main()
