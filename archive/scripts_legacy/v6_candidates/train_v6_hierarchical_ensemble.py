"""Research-only trainer for the legacy causal V6 H0--H3 hierarchy.

H0 preserves the original V6 three-model ensemble (XGBoost, LightGBM and
CatBoost) with the previously selected ``F_plus_accumulation_base`` features.
The second expert uses only the paper-derived technical indicators.  H1--H3
then follow the old hierarchy exactly: technical gate, causal logistic fusion,
and fusion plus technical gate.  The hierarchy is selected on walk-forward OOF
predictions only; final-holdout results are an explicitly descriptive replay.

This module is not part of the production-v1 path.  Production trains the
original V6 stock ensemble directly with ``train_v6_original_shadow.py`` and uses its
probability as ``p_v6_trend``.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
for directory in (ROOT, SCRIPT_DIR):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import train_v6_original_shadow as pipeline  # noqa: E402
from src.models.hierarchical_surge import (  # noqa: E402
    HierarchicalSurgeConfig,
    apply_daily_selection,
    causal_hierarchical_oof,
    fit_deployment_meta_model,
    join_expert_oof,
    select_technical_gate,
    selection_metrics,
    summarize_candidates,
)


LOCAL_DEFAULTS = {
    "data_dir": "data/vnstock/v6_snapshot",
    "market_path": "data/vnstock/v6_snapshot/market/VNINDEX.csv",
    "industry_path": "data/vnstock/v6_snapshot/industry_map.csv",
    "market_cap_path": "data/vnstock/v6_snapshot/symbols.csv",
}
EXPERT_FEATURES = {
    "stock": "F_plus_accumulation_base",
    "technical": "C_paper_all",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=3, help="Optuna trials per expert/model.")
    parser.add_argument("--compute-device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument(
        "--supervised-sample-stride",
        type=int,
        default=None,
        help="Sample every N dates in the selected weekday calendar.",
    )
    parser.add_argument(
        "--supervised-sample-weekday",
        type=int,
        choices=range(5),
        default=None,
        help="Optional ISO weekday selector: Monday=0 through Friday=4.",
    )
    parser.add_argument(
        "--supervised-sample-anchor-date",
        default=None,
        help="Market date that defines phase zero for stride-based sampling.",
    )
    parser.add_argument("--allow-stale-cache", action="store_true")
    parser.add_argument(
        "--reuse-experts",
        action="store_true",
        help="Reuse completed expert bundles and rerun only causal hierarchy evaluation.",
    )
    parser.add_argument(
        "--stock-weights",
        default="auto",
        help=(
            "H0 XGB,LGB,Cat weights. 'auto' uses the weights learned by the "
            "snapshot expert; pass three comma-separated values to reproduce "
            "the legacy fixed ensemble."
        ),
    )
    parser.add_argument(
        "--models-dir",
        type=Path,
        default=Path("models/wave_ignition/v6_hierarchical_ensemble"),
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=Path("eval/runs/v6_hierarchical_ensemble"),
    )
    parser.add_argument("--data-dir")
    parser.add_argument("--market-path")
    parser.add_argument("--industry-path")
    parser.add_argument("--market-cap-path")
    return parser.parse_args()


def expert_config(args: argparse.Namespace, name: str) -> pipeline.Config:
    values = asdict(pipeline.Config())
    values.update(LOCAL_DEFAULTS)
    for field in LOCAL_DEFAULTS:
        supplied = getattr(args, field)
        if supplied is not None:
            values[field] = supplied
    values.update(
        {
            "models_dir": str(args.models_dir / "experts" / name),
            "reports_dir": str(args.reports_dir / "experts" / name),
            "compute_device": args.compute_device,
            "optuna_trials": args.trials,
        }
    )
    if args.supervised_sample_stride is not None:
        values["supervised_sample_stride"] = args.supervised_sample_stride
    if args.supervised_sample_weekday is not None:
        values["supervised_sample_weekday"] = args.supervised_sample_weekday
    if args.supervised_sample_anchor_date is not None:
        values["supervised_sample_anchor_date"] = args.supervised_sample_anchor_date
    return pipeline.Config(**values)


def train_expert(args: argparse.Namespace, name: str) -> tuple[pipeline.Config, dict[str, Any]]:
    """Train one base ensemble while pinning its predeclared feature family."""
    feature_name = EXPERT_FEATURES[name]
    cfg = expert_config(args, name)
    original_experiments = pipeline.FEATURE_EXPERIMENTS
    try:
        pipeline.FEATURE_EXPERIMENTS = {feature_name: original_experiments[feature_name]}
        report = pipeline.train_pipeline(
            cfg,
            allow_stale_cache=args.allow_stale_cache,
            save_feature_store=False,
        )
    finally:
        pipeline.FEATURE_EXPERIMENTS = original_experiments
    return cfg, report


def inner_calibration_split(
    fold_train: pd.DataFrame, cfg: pipeline.Config
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reserve only the latest resolved dates of a fold for temporal calibration."""
    return pipeline.nested_calibration_split(fold_train, cfg)


def load_bundle(cfg: pipeline.Config) -> dict[str, Any]:
    path = Path(cfg.models_dir) / "evaluation_bundle.joblib"
    if not path.is_file():
        raise FileNotFoundError(f"Expert bundle was not created: {path}")
    return joblib.load(path)


def parse_weights(value: str) -> np.ndarray | None:
    if value.strip().lower() == "auto":
        return None
    weights = np.array([float(item.strip()) for item in value.split(",")], dtype=float)
    if weights.shape != (len(pipeline.MODEL_NAMES),) or (weights < 0).any():
        raise ValueError("--stock-weights must contain three non-negative XGB,LGB,Cat values")
    if not np.isclose(float(weights.sum()), 1.0):
        raise ValueError("--stock-weights must sum to 1.0")
    return weights


def expert_oof(
    name: str,
    bundle: dict[str, Any],
    train: pd.DataFrame,
    folds: list[tuple[np.ndarray, np.ndarray, dict[str, str]]],
    cfg: pipeline.Config,
    fixed_weights: np.ndarray | None = None,
) -> pd.DataFrame:
    """Create temporally calibrated OOF ensemble scores for one expert."""
    feature_name = str(bundle["feature_experiment"])
    candidate_features = pipeline.FEATURE_EXPERIMENTS[feature_name]
    params = bundle["best_params"]
    rows: list[pd.DataFrame] = []
    for train_idx, validation_idx, fold_meta in folds:
        fold_train = train.iloc[train_idx].copy()
        validation = train.iloc[validation_idx].copy()
        core, calibration = inner_calibration_split(fold_train, cfg)
        processor = pipeline.fit_feature_processor(core, cfg, candidate_features)
        models = pipeline.fit_models(core, params, processor, cfg)
        cal_raw = pipeline.raw_probability_matrix(models, calibration, processor)
        cal_weight = pipeline.date_balanced_weights(calibration)
        calibrators = pipeline.fit_individual_calibrators(
            cal_raw,
            calibration["wave_entry"].to_numpy(int),
            cfg.random_seed,
            cal_weight,
        )
        cal_matrix = pipeline.apply_individual_calibrators(cal_raw, calibrators)
        weights = (
            fixed_weights.copy()
            if fixed_weights is not None
            else pipeline.learn_ensemble_weights(
                cal_matrix,
                calibration,
                np.ones(len(pipeline.MODEL_NAMES), dtype=bool),
                cfg,
            )
        )
        cal_pre_platt = cal_matrix @ weights
        ensemble_calibrator = pipeline.fit_platt_calibrator(
            cal_pre_platt,
            calibration["wave_entry"].to_numpy(int),
            cfg.random_seed,
            cal_weight,
        )
        val_raw = pipeline.raw_probability_matrix(models, validation, processor)
        val_matrix = pipeline.apply_individual_calibrators(val_raw, calibrators)
        pre_platt = val_matrix @ weights
        temporal_probability = pipeline.apply_platt(ensemble_calibrator, pre_platt)
        rows.append(
            pd.DataFrame(
                {
                    "fold_id": str(fold_meta["fold"]),
                    "symbol": validation["ticker"].astype(str).to_numpy(),
                    "date": pd.to_datetime(validation["time"]).to_numpy(),
                    "y_entry": validation["wave_entry"].to_numpy(int),
                    "sample_weight": pipeline.event_uniqueness_weights(validation),
                    "p_entry_raw": pre_platt,
                    "p_entry_calibrated_temporal": temporal_probability,
                    "ensemble_weight_xgb": weights[0],
                    "ensemble_weight_lgb": weights[1],
                    "ensemble_weight_cat": weights[2],
                    "expert": name,
                }
            )
        )
    return pd.concat(rows, ignore_index=True).sort_values(["fold_id", "date", "symbol"]).reset_index(drop=True)


def predict_expert_bundle(
    bundle: dict[str, Any], frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Return pre- and post-Platt ensemble probabilities from a fitted expert."""
    raw = pipeline.raw_probability_matrix(bundle["models"], frame, bundle["feature_processor"])
    matrix = pipeline.apply_individual_calibrators(raw, bundle["individual_calibrators"])
    weights = np.array(
        [bundle["ensemble_weights"][model] for model in pipeline.MODEL_NAMES], dtype=float
    )
    pre_platt = matrix @ weights
    return pre_platt, pipeline.apply_platt(bundle["ensemble_calibrator"], pre_platt)


def with_fixed_ensemble_calibration(
    bundle: dict[str, Any], calibration: pd.DataFrame, weights: np.ndarray
) -> dict[str, Any]:
    """Refit only the ensemble Platt layer after declaring fixed H0 weights."""
    result = dict(bundle)
    raw = pipeline.raw_probability_matrix(
        result["models"], calibration, result["feature_processor"]
    )
    matrix = pipeline.apply_individual_calibrators(raw, result["individual_calibrators"])
    pre_platt = matrix @ weights
    result["ensemble_weights"] = dict(zip(pipeline.MODEL_NAMES, weights.tolist()))
    result["ensemble_calibrator"] = pipeline.fit_platt_calibrator(
        pre_platt,
        calibration["wave_entry"].to_numpy(int),
        int(result["config"]["random_seed"]),
        pipeline.date_balanced_weights(calibration),
    )
    return result


def selection_frame(
    test: pd.DataFrame,
    stock_raw: np.ndarray,
    technical_raw: np.ndarray,
    h2: np.ndarray,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(test["time"]).to_numpy(),
            "symbol": test["ticker"].astype(str).to_numpy(),
            "y_entry": test["wave_entry"].to_numpy(int),
            "sample_weight": pipeline.event_uniqueness_weights(test),
            "p_h0": stock_raw,
            "p_technical_raw": technical_raw,
            "p_h2": h2,
        }
    )


def final_hierarchy_metrics(
    test: pd.DataFrame,
    stock_raw: np.ndarray,
    stock_probability: np.ndarray,
    technical_raw: np.ndarray,
    meta_model: Any,
    h1_policy: dict[str, Any],
    h3_policy: dict[str, Any],
    hierarchy_cfg: HierarchicalSurgeConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Replay H0--H3 on final dates without feeding outcomes back into policies."""
    live = selection_frame(test, stock_raw, technical_raw, np.zeros(len(test)))
    live = pipeline_frame_percentiles(live)
    h2 = meta_model.predict_proba(
        live.rename(
            columns={"p_h0": "p_stock_raw"}, errors="raise"
        )
    )
    live["p_h2"] = h2
    threshold_h1 = float(h1_policy.get("threshold", float("nan")))
    threshold_h3 = float(h3_policy.get("threshold", float("nan")))
    variants = {
        "H0_stock_ensemble": ("p_h0", None),
        "H1_stock_plus_technical_gate": (
            "p_h0",
            live["p_technical_raw"].ge(threshold_h1) if np.isfinite(threshold_h1) else pd.Series(False, index=live.index),
        ),
        "H2_causal_logistic_fusion": ("p_h2", None),
        "H3_fusion_plus_technical_gate": (
            "p_h2",
            live["p_technical_raw"].ge(threshold_h3) if np.isfinite(threshold_h3) else pd.Series(False, index=live.index),
        ),
    }
    selection_rows: list[dict[str, Any]] = []
    selected_columns: dict[str, pd.Series] = {}
    for candidate, (score, gate) in variants.items():
        selected = apply_daily_selection(live, score_column=score, top_k=hierarchy_cfg.top_k, gate=gate)
        selected_columns[candidate] = selected["selected"]
        selection_rows.append({"candidate": candidate, **selection_metrics(selected)})
    probability_rows = [
        {"candidate": "H0_stock_ensemble", **pipeline.classification_metrics(test, stock_probability, 0.5, hierarchy_cfg.top_k)},
        {"candidate": "H2_causal_logistic_fusion", **pipeline.classification_metrics(test, h2, 0.5, hierarchy_cfg.top_k)},
    ]
    live["p_h0_calibrated"] = stock_probability
    live["p_h2"] = h2
    for candidate, selected in selected_columns.items():
        live[f"selected_{candidate}"] = selected.to_numpy(bool)
    return pd.DataFrame(selection_rows), pd.DataFrame(probability_rows), live


def pipeline_frame_percentiles(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["stock_daily_percentile"] = result.groupby("date", observed=True)["p_h0"].rank(
        pct=True, ascending=True, method="average"
    )
    result["technical_daily_percentile"] = result.groupby("date", observed=True)["p_technical_raw"].rank(
        pct=True, ascending=True, method="average"
    )
    return result


def main() -> None:
    args = parse_args()
    if args.trials <= 0:
        raise ValueError("--trials must be positive")
    args.models_dir.mkdir(parents=True, exist_ok=True)
    args.reports_dir.mkdir(parents=True, exist_ok=True)
    fixed_stock_weights = parse_weights(args.stock_weights)
    stock_cfg = expert_config(args, "stock")
    technical_cfg = expert_config(args, "technical")
    if args.reuse_experts:
        print("[1/5] Reusing completed stock and technical expert bundles")
    else:
        print("[1/5] Training stock expert: original V6 XGB + LGB + Cat ensemble")
        train_expert(args, "stock")
        print("[2/5] Training technical expert: paper-indicator XGB + LGB + Cat ensemble")
        train_expert(args, "technical")
    stock_bundle = load_bundle(stock_cfg)
    technical_bundle = load_bundle(technical_cfg)

    print("[3/5] Generating strictly temporal OOF expert predictions for H0--H3")
    panel, _, _ = pipeline.build_panel(stock_cfg, allow_stale_cache=args.allow_stale_cache)
    labelled, _ = pipeline.prepare_samples(panel, stock_cfg)
    market_dates = np.array(sorted(panel["time"].dropna().unique()))
    train, calibration, test, boundaries = pipeline.split_train_calibration_test(
        labelled, market_dates, stock_cfg
    )
    if fixed_stock_weights is not None:
        # Fixed weights remain available for an explicit legacy reproduction,
        # but are no longer the default because the snapshot expert performs
        # causal admission and may reject weak ensemble members.
        stock_bundle = with_fixed_ensemble_calibration(
            stock_bundle, calibration, fixed_stock_weights
        )
    folds = pipeline.purged_walk_forward_folds(train, stock_cfg)
    stock_oof = expert_oof(
        "stock", stock_bundle, train, folds, stock_cfg, fixed_weights=fixed_stock_weights
    )
    technical_oof = expert_oof("technical", technical_bundle, train, folds, technical_cfg)
    stock_oof.to_parquet(args.reports_dir / "stock_expert_oof.parquet", index=False)
    technical_oof.to_parquet(args.reports_dir / "technical_expert_oof.parquet", index=False)
    joined = join_expert_oof(
        stock_oof.rename(
            columns={
                "p_entry_raw": "p_stock_raw",
                "p_entry_calibrated_temporal": "p_stock_calibrated_temporal",
            }
        ),
        technical_oof.rename(
            columns={
                "p_entry_raw": "p_technical_raw",
                "p_entry_calibrated_temporal": "p_technical_calibrated_temporal",
            }
        ),
    )
    hierarchy_cfg = HierarchicalSurgeConfig(top_k=stock_cfg.top_k_per_day)
    hierarchical_oof, fold_metrics, gate_audit = causal_hierarchical_oof(joined, hierarchy_cfg)
    oof_summary = summarize_candidates(hierarchical_oof, hierarchy_cfg)
    hierarchical_oof.to_parquet(args.reports_dir / "hierarchical_oof.parquet", index=False)
    fold_metrics.to_csv(args.reports_dir / "hierarchical_fold_metrics.csv", index=False)
    gate_audit.to_csv(args.reports_dir / "hierarchical_gate_audit.csv", index=False)

    print("[4/5] Fitting final hierarchy from OOF only and replaying the observed final holdout")
    meta_model = fit_deployment_meta_model(joined, hierarchy_cfg)
    h1_policy = select_technical_gate(joined, score_column="p_stock_raw", config=hierarchy_cfg)
    h3_history = hierarchical_oof.loc[hierarchical_oof["p_h2"].notna()].copy()
    h3_policy = select_technical_gate(h3_history, score_column="p_h2", config=hierarchy_cfg)
    stock_raw, stock_probability = predict_expert_bundle(stock_bundle, test)
    technical_raw, _ = predict_expert_bundle(technical_bundle, test)
    final_selection, final_probability, final_predictions = final_hierarchy_metrics(
        test,
        stock_raw,
        stock_probability,
        technical_raw,
        meta_model,
        h1_policy,
        h3_policy,
        hierarchy_cfg,
    )
    final_selection.to_csv(args.reports_dir / "hierarchical_final_selection_replay.csv", index=False)
    final_probability.to_csv(args.reports_dir / "hierarchical_final_probability_replay.csv", index=False)
    final_predictions.to_csv(args.reports_dir / "hierarchical_final_predictions_replay.csv", index=False)

    print("[5/5] Saving deployable hierarchy bundle and causal audit")
    deployment_bundle = {
        "pipeline_version": "v6_hierarchical_ensemble_v1",
        "status": "candidate_oof_selected_final_holdout_replay_only",
        "stock_expert": stock_bundle,
        "technical_expert": technical_bundle,
        "meta_model": meta_model,
        "hierarchy_config": hierarchy_cfg.to_dict(),
        "h1_technical_gate": h1_policy,
        "h3_technical_gate": h3_policy,
        "split_boundaries": boundaries,
        "compute_device_training": args.compute_device,
        "stock_ensemble_weights": dict(
            zip(
                pipeline.MODEL_NAMES,
                (
                    fixed_stock_weights
                    if fixed_stock_weights is not None
                    else np.array(
                        [stock_bundle["ensemble_weights"][name] for name in pipeline.MODEL_NAMES],
                        dtype=float,
                    )
                ).tolist(),
            )
        ),
        "stock_ensemble_weight_policy": (
            "explicit_fixed_legacy" if fixed_stock_weights is not None else "snapshot_learned"
        ),
        "warning": (
            "H0--H3 policy selection used causal walk-forward OOF predictions only. "
            "The final holdout had been observed earlier and is descriptive replay only."
        ),
    }
    joblib.dump(deployment_bundle, args.models_dir / "evaluation_bundle.joblib", compress=3)
    report = {
        "status": "candidate_oof_selected_final_holdout_replay_only",
        "architecture": {
            "H0": "original V6 ensemble stock expert",
            "H1": "H0 ranking with paper-technical hard gate",
            "H2": "causal logistic fusion of stock and technical experts",
            "H3": "H2 ranking with paper-technical hard gate",
        },
        "data_contract": {
            "snapshot": stock_cfg.data_dir,
            "feature_groups": EXPERT_FEATURES,
            "target": stock_bundle["data_meta"]["target_definition"],
            "split_boundaries": boundaries,
        },
        "training": {
            "models": list(pipeline.MODEL_NAMES),
            "compute_device": args.compute_device,
            "lightgbm_note": "LightGBM uses the installed CPU build; XGBoost and CatBoost use CUDA.",
            "optuna_trials_per_expert_model": args.trials,
            "stock_ensemble_weights": dict(
                zip(
                    pipeline.MODEL_NAMES,
                    (
                        fixed_stock_weights
                        if fixed_stock_weights is not None
                        else np.array(
                            [stock_bundle["ensemble_weights"][name] for name in pipeline.MODEL_NAMES],
                            dtype=float,
                        )
                    ).tolist(),
                )
            ),
            "stock_ensemble_weight_policy": (
                "explicit_fixed_legacy" if fixed_stock_weights is not None else "snapshot_learned"
            ),
        },
        "oof_summary": oof_summary,
        "final_holdout_replay_selection": final_selection.to_dict(orient="records"),
        "final_holdout_replay_probability": final_probability.to_dict(orient="records"),
        "h1_policy": h1_policy,
        "h3_policy": h3_policy,
        "stock_expert_report": str(Path(stock_cfg.reports_dir)),
        "technical_expert_report": str(Path(technical_cfg.reports_dir)),
    }
    (args.reports_dir / "hierarchical_evaluation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print("\nOOF candidate summary:")
    print(json.dumps(oof_summary, ensure_ascii=False, indent=2, default=str))
    print("\nFinal-holdout replay selection metrics:")
    print(final_selection.to_string(index=False))
    print(f"\nSaved hierarchy bundle: {args.models_dir / 'evaluation_bundle.joblib'}")


if __name__ == "__main__":
    main()
