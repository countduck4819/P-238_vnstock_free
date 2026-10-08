"""Phase-C reporting for comparable daily H120 ranker experiments."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

RANKING_METRICS = ("precision_at_k", "map_at_k", "ndcg_at_k", "lift")


def summarize_daily_ranking_metrics(
    daily: pd.DataFrame,
    predictions: pd.DataFrame,
    *,
    metrics: tuple[str, ...] = RANKING_METRICS,
) -> dict[str, Any]:
    """Summarize daily ranking metrics overall and by registered fold."""
    if daily["date"].duplicated().any():
        raise ValueError("Daily ranking metrics must contain one row per date.")
    required = {"date", "fold_id"}
    missing = sorted(required.difference(predictions.columns))
    if missing:
        raise ValueError(f"Predictions are missing fold metadata: {missing}")
    date_folds = predictions.loc[:, ["date", "fold_id"]].drop_duplicates().copy()
    if date_folds["date"].duplicated().any():
        raise ValueError("Each prediction date must map to exactly one fold.")
    result = daily.merge(date_folds, on="date", how="inner", validate="one_to_one")
    if len(result) != len(daily):
        raise ValueError("Every daily metric date must have a prediction fold.")
    summary: dict[str, Any] = {"days": int(len(result)), "folds": sorted(result["fold_id"].unique())}
    for metric in metrics:
        if metric not in result:
            raise ValueError(f"Daily metrics are missing {metric}.")
        by_fold = result.groupby("fold_id", observed=True, sort=True)[metric].mean()
        summary[metric] = {
            "mean": float(result[metric].mean()),
            "worst_fold": float(by_fold.min()),
            "fold_means": {str(fold): float(value) for fold, value in by_fold.items()},
        }
    return summary


def summarize_seed_metric_reports(
    reports: Mapping[int, dict[str, Any]],
    *,
    metrics: tuple[str, ...] = RANKING_METRICS,
) -> dict[str, Any]:
    """Aggregate Phase-C R2 confirmation runs without pooling daily dates."""
    if not reports:
        raise ValueError("At least one seed report is required.")
    expected_folds: tuple[str, ...] | None = None
    aggregate: dict[str, Any] = {"seeds": sorted(int(seed) for seed in reports)}
    for metric in metrics:
        means: list[float] = []
        worst_folds: list[float] = []
        for seed, report in reports.items():
            folds = tuple(report["folds"])
            if expected_folds is None:
                expected_folds = folds
            elif folds != expected_folds:
                raise ValueError(f"Seed {seed} uses different folds: {folds} != {expected_folds}")
            values = report[metric]
            means.append(float(values["mean"]))
            worst_folds.append(float(values["worst_fold"]))
        aggregate[metric] = {
            "seed_mean": float(np.mean(means)),
            "seed_std": float(np.std(means, ddof=0)),
            "worst_fold_over_seeds": float(np.min(worst_folds)),
        }
    aggregate["folds"] = list(expected_folds or ())
    return aggregate
