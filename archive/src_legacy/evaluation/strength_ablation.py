"""Paired, temporal evaluation for conditional-strength prediction heads."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

KEY_COLUMNS = ["fold_id", "symbol", "date"]
REQUIRED_COLUMNS = {*KEY_COLUMNS, "y_entry", "y_strength", "sample_weight", "p_strength"}


def load_strength_oof(path: str) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    missing = sorted(REQUIRED_COLUMNS - set(frame.columns))
    if missing:
        raise ValueError(f"Strength OOF is missing columns: {missing}")
    result = frame.loc[:, list(REQUIRED_COLUMNS)].copy()
    result["date"] = pd.to_datetime(result["date"], errors="raise").dt.normalize()
    if result.duplicated(KEY_COLUMNS).any():
        raise ValueError("Strength OOF contains duplicate keys.")
    return result


def strength_metrics(frame: pd.DataFrame) -> dict[str, float]:
    positive = frame.loc[frame["y_entry"].eq(1) & frame["y_strength"].notna()].copy()
    if positive.empty:
        return {"positive_rows": 0.0, "weighted_mae": float("nan"), "weighted_rmse": float("nan"), "spearman": float("nan")}
    target = positive["y_strength"].to_numpy(dtype=float)
    predicted = positive["p_strength"].to_numpy(dtype=float)
    weight = positive["sample_weight"].to_numpy(dtype=float)
    error = target - predicted
    correlation = spearmanr(target, predicted).statistic if len(positive) >= 3 else float("nan")
    return {
        "positive_rows": float(len(positive)),
        "weighted_mae": float(np.average(np.abs(error), weights=weight)),
        "weighted_rmse": float(np.sqrt(np.average(np.square(error), weights=weight))),
        "spearman": float(correlation) if np.isfinite(correlation) else float("nan"),
    }


def compare_strength_paired(
    baseline: pd.DataFrame, candidate: pd.DataFrame
) -> tuple[dict[str, Any], pd.DataFrame]:
    candidate = candidate.rename(columns={"p_strength": "p_strength_candidate"})
    baseline = baseline.rename(columns={"p_strength": "p_strength_baseline"})
    shared = [*KEY_COLUMNS, "y_entry", "y_strength", "sample_weight"]
    paired = baseline[shared + ["p_strength_baseline"]].merge(
        candidate[shared + ["p_strength_candidate"]],
        on=KEY_COLUMNS,
        how="inner",
        suffixes=("_baseline", "_candidate"),
        validate="one_to_one",
    )
    if len(paired) != len(baseline) or len(paired) != len(candidate):
        raise ValueError("Strength OOF key coverage differs.")
    for column in ("y_entry", "y_strength", "sample_weight"):
        left = paired[f"{column}_baseline"]
        right = paired[f"{column}_candidate"]
        if not np.allclose(left, right, equal_nan=True):
            raise ValueError(f"Strength OOF {column} differs between candidates.")
        paired[column] = left
    baseline_metrics = strength_metrics(
        paired.rename(columns={"p_strength_baseline": "p_strength"})
    )
    candidate_metrics = strength_metrics(
        paired.rename(columns={"p_strength_candidate": "p_strength"})
    )
    folds: list[dict[str, Any]] = []
    for fold_id, group in paired.groupby("fold_id", sort=True):
        base = strength_metrics(group.rename(columns={"p_strength_baseline": "p_strength"}))
        tested = strength_metrics(group.rename(columns={"p_strength_candidate": "p_strength"}))
        folds.append(
            {
                "fold_id": fold_id,
                "base_weighted_mae": base["weighted_mae"],
                "candidate_weighted_mae": tested["weighted_mae"],
                "delta_weighted_mae": tested["weighted_mae"] - base["weighted_mae"],
                "base_spearman": base["spearman"],
                "candidate_spearman": tested["spearman"],
                "delta_spearman": tested["spearman"] - base["spearman"],
                "positive_rows": tested["positive_rows"],
            }
        )
    summary = {
        "paired_rows": int(len(paired)),
        "baseline": baseline_metrics,
        "candidate": candidate_metrics,
        "mae_relative_improvement": 1.0
        - candidate_metrics["weighted_mae"] / baseline_metrics["weighted_mae"],
        "spearman_delta": candidate_metrics["spearman"] - baseline_metrics["spearman"],
    }
    return summary, pd.DataFrame(folds)
