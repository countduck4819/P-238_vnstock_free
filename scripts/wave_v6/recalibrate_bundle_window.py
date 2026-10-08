"""Refit V6 probability calibrators on a fixed historical date window.

This runner deliberately keeps the saved base models, feature processor and
ensemble weights unchanged.  It only rebuilds the labelled panel to obtain a
chosen calibration population, refits the per-model and ensemble Platt
calibrators, then compares the latest ranking before and after refitting.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path

import joblib
import numpy as np
import pandas as pd


def load_trainer():
    script_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(script_dir))
    spec = importlib.util.spec_from_file_location(
        "wave_v6_trainer", script_dir / "train_v6_original_shadow.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load V6 training module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--market-path", type=Path, required=True)
    parser.add_argument("--industry-path", type=Path, required=True)
    parser.add_argument("--market-cap-path", type=Path, required=True)
    parser.add_argument("--calibration-start", required=True)
    parser.add_argument("--calibration-end", required=True,
                        help="Exclusive calibration end / original test-start date")
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    trainer = load_trainer()
    bundle = joblib.load(args.bundle)
    cfg = replace(
        trainer.Config(**bundle["config"]),
        data_dir=str(args.data_dir),
        market_path=str(args.market_path),
        industry_path=str(args.industry_path),
        market_cap_path=str(args.market_cap_path),
        models_dir=str(args.output_dir),
        reports_dir=str(args.output_dir),
    )

    print("Building labelled panel for calibration-only refit...", flush=True)
    panel, _, _ = trainer.build_panel(cfg, allow_stale_cache=True, include_targets=True)
    labelled, _ = trainer.prepare_samples(panel, cfg)
    start = pd.Timestamp(args.calibration_start)
    end = pd.Timestamp(args.calibration_end)
    calibration = labelled.loc[
        (labelled["time"] >= start)
        & (labelled["time"] < end)
        & (labelled["label_end_time"] < end)
    ].copy()
    if calibration.empty or calibration["wave_entry"].nunique() < 2:
        raise RuntimeError("Fixed calibration window is empty or has one class")

    models = bundle["models"]
    processor = bundle["feature_processor"]
    weights = np.asarray(
        [float(bundle["ensemble_weights"][name]) for name in trainer.MODEL_NAMES], dtype=float
    )
    if not np.isclose(weights.sum(), 1.0):
        raise RuntimeError("Saved ensemble weights do not sum to one")

    y_cal = calibration["wave_entry"].to_numpy(int)
    cal_weight = trainer.date_balanced_weights(calibration)
    cal_raw = trainer.raw_probability_matrix(models, calibration, processor)
    calibrators = trainer.fit_individual_calibrators(cal_raw, y_cal, cfg.random_seed, cal_weight)
    cal_matrix = trainer.apply_individual_calibrators(cal_raw, calibrators)
    ensemble_calibrator = trainer.fit_platt_calibrator(
        cal_matrix @ weights, y_cal, cfg.random_seed, cal_weight
    )

    latest_candidates = panel.loc[panel["eligible"].fillna(False)].copy()
    latest_candidates = latest_candidates.loc[
        latest_candidates[processor["features"]].notna().mean(axis=1) >= cfg.min_row_feature_coverage
    ]
    latest_date = latest_candidates["time"].max()
    latest = latest_candidates.loc[latest_candidates["time"].eq(latest_date)].copy()
    if latest.empty:
        raise RuntimeError("No eligible latest candidates")
    latest["market_cap"] = latest["ticker"].map(
        trainer.load_market_cap_map(Path(cfg.market_cap_path))
    )
    latest_raw = trainer.raw_probability_matrix(models, latest, processor)

    original_matrix = trainer.apply_individual_calibrators(
        latest_raw, bundle["individual_calibrators"]
    )
    original_prob = trainer.apply_platt(
        bundle["ensemble_calibrator"], original_matrix @ weights
    )
    refit_matrix = trainer.apply_individual_calibrators(latest_raw, calibrators)
    refit_prob = trainer.apply_platt(ensemble_calibrator, refit_matrix @ weights)

    comparison = latest[["time", "ticker"]].copy()
    comparison["p_before_pct"] = original_prob * 100.0
    comparison["p_refit_pct"] = refit_prob * 100.0
    comparison["delta_pp"] = comparison["p_refit_pct"] - comparison["p_before_pct"]
    comparison = comparison.sort_values("p_refit_pct", ascending=False).reset_index(drop=True)
    comparison.index = comparison.index + 1
    comparison.index.name = "rank_refit"
    comparison.to_csv(args.output_dir / "latest_probability_before_after.csv")

    top50 = trainer.build_latest_ranking(latest, refit_matrix, refit_prob, weights, cfg)
    top50.to_csv(args.output_dir / "top50_refit_calibration.csv", index=False)

    refit_bundle = dict(bundle)
    refit_bundle["individual_calibrators"] = calibrators
    refit_bundle["ensemble_calibrator"] = ensemble_calibrator
    refit_bundle["calibration_method"] = (
        "date-balanced, lead-time-relevance-weighted Platt scaling; "
        f"refit only on [{start.date()}, {end.date()})"
    )
    refit_bundle["calibration_refit_window"] = {
        "start": str(start.date()), "end_exclusive": str(end.date()),
        "samples": int(len(calibration)),
        "raw_positive_rate": float(y_cal.mean()),
        "weighted_positive_rate": float(np.average(y_cal, weights=cal_weight)),
    }
    joblib.dump(refit_bundle, args.output_dir / "evaluation_bundle_refit_calibration.joblib", compress=3)

    report = {
        "base_bundle": str(args.bundle.resolve()),
        "latest_date": str(pd.Timestamp(latest_date).date()),
        "latest_symbols": int(len(latest)),
        "feature_experiment": bundle["feature_experiment"],
        "ensemble_weights": bundle["ensemble_weights"],
        "calibration_window": refit_bundle["calibration_refit_window"],
        "top1_before": comparison.iloc[0][["ticker", "p_before_pct"]].to_dict(),
        "top1_refit": comparison.iloc[0][["ticker", "p_refit_pct"]].to_dict(),
    }
    (args.output_dir / "calibration_refit_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
