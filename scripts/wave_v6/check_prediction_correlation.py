"""Audit Pearson correlation between XGB/LGB/CatBoost holdout probabilities."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


MODEL_COLUMNS = ("xgb", "lgb", "cat")


def prediction_correlation_report(
    predictions: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Return a Pearson matrix and an automatic diversity conclusion.

    The high/diverse conclusions require every one of the three pairwise
    correlations to cross the stated threshold. Mixed cases are reported
    separately instead of being forced into either conclusion.
    """
    missing = [column for column in MODEL_COLUMNS if column not in predictions.columns]
    if missing:
        raise ValueError(f"Missing prediction column(s): {missing}")

    probabilities = predictions.loc[:, MODEL_COLUMNS].apply(
        pd.to_numeric, errors="coerce"
    )
    if probabilities.isna().any().any():
        bad_rows = int(probabilities.isna().any(axis=1).sum())
        raise ValueError(f"Prediction data contain {bad_rows} row(s) with missing/non-numeric values")
    if len(probabilities) < 2:
        raise ValueError("At least two holdout rows are required for Pearson correlation")

    correlation = probabilities.corr(method="pearson")
    raw_pairs = {
        "xgb_lgb": float(correlation.loc["xgb", "lgb"]),
        "xgb_cat": float(correlation.loc["xgb", "cat"]),
        "lgb_cat": float(correlation.loc["lgb", "cat"]),
    }
    finite_pairwise = np.asarray(
        [value for value in raw_pairs.values() if np.isfinite(value)], dtype=float
    )
    pairs = {
        key: (value if np.isfinite(value) else None)
        for key, value in raw_pairs.items()
    }
    if finite_pairwise.size != 3:
        conclusion = (
            "At least one model has constant/invalid predictions; prediction diversity "
            "cannot be assessed reliably."
        )
    elif np.all(finite_pairwise > 0.95):
        conclusion = (
            "Models produce highly similar predictions, ensemble benefit is limited."
        )
    elif np.all(finite_pairwise < 0.85):
        conclusion = (
            "Models provide diverse predictions, ensemble may improve robustness."
        )
    else:
        conclusion = (
            "Models show mixed prediction similarity; ensemble benefit must be judged "
            "together with holdout PR-AUC, Lift@50 and calibration."
        )

    summary: dict[str, Any] = {
        "method": "pearson",
        "probability_type": "raw_predict_proba_class_1",
        "rows": int(len(probabilities)),
        "pairwise": pairs,
        "pairwise_mean": (
            float(finite_pairwise.mean()) if finite_pairwise.size else None
        ),
        "all_pairwise_above_0_95": bool(
            finite_pairwise.size == 3 and np.all(finite_pairwise > 0.95)
        ),
        "all_pairwise_below_0_85": bool(
            finite_pairwise.size == 3 and np.all(finite_pairwise < 0.85)
        ),
        "conclusion": conclusion,
        "matrix": {
            row: {
                column: (
                    float(correlation.loc[row, column])
                    if np.isfinite(correlation.loc[row, column]) else None
                )
                for column in MODEL_COLUMNS
            }
            for row in MODEL_COLUMNS
        },
    }
    return correlation, summary


def print_prediction_correlation(
    correlation: pd.DataFrame,
    conclusion: str,
) -> None:
    print("\nPrediction correlation:")
    print(correlation.to_string(float_format=lambda value: f"{value:.6f}"))
    print(f"\nConclusion: {conclusion}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--predictions",
        type=Path,
        default=Path("reports_wave_v6/final_holdout_raw_predictions.csv"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports_wave_v6/prediction_correlation_final_holdout.csv"),
    )
    parser.add_argument(
        "--evaluation-report",
        type=Path,
        default=Path("reports_wave_v6/evaluation_report.json"),
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    predictions = pd.read_csv(args.predictions)
    correlation, summary = prediction_correlation_report(predictions)
    print_prediction_correlation(correlation, str(summary["conclusion"]))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    correlation.to_csv(args.output, index=True, index_label="model")

    if args.evaluation_report.exists():
        report = json.loads(args.evaluation_report.read_text(encoding="utf-8"))
    else:
        report = {}
    report["prediction_correlation_final_holdout"] = summary
    args.evaluation_report.parent.mkdir(parents=True, exist_ok=True)
    args.evaluation_report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Saved correlation: {args.output}")
    print(f"Updated evaluation report: {args.evaluation_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
