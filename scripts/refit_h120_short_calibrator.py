"""Causally refit and audit the deployed H120 cascade probability calibrator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.training.h120_ranker_calibration import expected_calibration_error
from src.training.xgboost_pipeline import SigmoidCalibration, fit_sigmoid_calibration


def metrics(frame: pd.DataFrame, probability: np.ndarray) -> dict[str, float]:
    y = frame["y_cont_h120"].to_numpy(int)
    w = frame["sample_weight"].to_numpy(float)
    return {
        "brier": float(brier_score_loss(y, probability, sample_weight=w)),
        "log_loss": float(log_loss(y, probability, sample_weight=w, labels=[0, 1])),
        "ece": float(expected_calibration_error(y, probability, w, bins=10)),
        "predicted_prevalence": float(np.average(probability, weights=w)),
        "observed_prevalence": float(np.average(y, weights=w)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--oof", type=Path, required=True)
    parser.add_argument("--live-predictions", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    oof = pd.read_parquet(args.oof)
    valid = oof.loc[
        oof[["fold_id", "p_cascade", "p_cascade_calibrated", "y_cont_h120", "sample_weight"]]
        .notna().all(axis=1)
    ].copy()
    folds = sorted(valid["fold_id"].astype(str).unique())
    if len(folds) < 2:
        raise RuntimeError("Need at least two valid causal OOF folds")
    audit_fold = folds[-1]
    train = valid.loc[valid["fold_id"].astype(str).lt(audit_fold)].copy()
    audit = valid.loc[valid["fold_id"].astype(str).eq(audit_fold)].copy()
    calibrator = fit_sigmoid_calibration(
        train["p_cascade"], train["y_cont_h120"], train["sample_weight"], random_seed=238
    )
    candidate = calibrator.predict(audit["p_cascade"])
    baseline = audit["p_cascade_calibrated"].to_numpy(float)
    baseline_metrics = metrics(audit, baseline)
    candidate_metrics = metrics(audit, candidate)
    passed = (
        candidate_metrics["brier"] <= baseline_metrics["brier"] + 1e-9
        and candidate_metrics["log_loss"] <= baseline_metrics["log_loss"] + 1e-9
    )

    live = pd.read_parquet(args.live_predictions)
    live["p_cascade_refit_candidate"] = calibrator.predict(live["p_cascade"])
    live["delta_pp"] = (live["p_cascade_refit_candidate"] - live["p_cascade_calibrated"]) * 100.0
    live.to_parquet(args.output_dir / "live_predictions_before_after.parquet", index=False)
    candidate_payload = calibrator.to_dict()
    candidate_payload.update({
        "fit_policy": "causal_prior_oof_folds_only",
        "fit_folds": [fold for fold in folds if fold != audit_fold],
        "audit_fold": audit_fold,
        "accepted_by_brier_and_log_loss": passed,
    })
    (args.output_dir / "calibration_candidate.json").write_text(
        json.dumps(candidate_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    report = {
        "audit_fold": audit_fold,
        "fit_rows": int(len(train)),
        "audit_rows": int(len(audit)),
        "baseline_temporal_metrics": baseline_metrics,
        "candidate_metrics": candidate_metrics,
        "candidate": candidate_payload,
        "live_top1_before": live.sort_values("p_cascade_calibrated", ascending=False).iloc[0][
            ["symbol", "p_cascade", "p_cascade_calibrated"]
        ].to_dict(),
        "live_top1_candidate": live.sort_values("p_cascade_refit_candidate", ascending=False).iloc[0][
            ["symbol", "p_cascade_refit_candidate", "delta_pp"]
        ].to_dict(),
    }
    (args.output_dir / "calibration_refit_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
