"""Paired OOF comparison utilities for feature-set experiments."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score


def feature_redundancy_metrics(
    frame: pd.DataFrame,
    *,
    reference_features: set[str] | None = None,
) -> dict[str, Any]:
    """Measure rank redundancy, emphasizing features added to a baseline."""
    numeric = frame.apply(pd.to_numeric, errors="coerce")
    usable = [column for column in numeric if numeric[column].nunique(dropna=True) > 1]
    if not usable:
        return {
            "usable_feature_count": 0,
            "effective_rank": 0.0,
            "effective_rank_fraction": 0.0,
            "maximum_absolute_spearman": float("nan"),
            "maximum_correlation_pair": [],
        }
    added = set(usable) - (reference_features or set())
    rank_scope = [
        feature
        for feature in usable
        if reference_features is None or feature in added
    ]
    if not rank_scope:
        return {
            "usable_feature_count": len(usable),
            "effective_rank_feature_count": 0,
            "effective_rank_scope": "added_features",
            "effective_rank": 0.0,
            "effective_rank_fraction": 0.0,
            "maximum_absolute_spearman": float("nan"),
            "maximum_correlation_pair": [],
        }
    rank_correlation = numeric[rank_scope].corr(
        method="spearman", min_periods=100
    ).fillna(0.0)
    np.fill_diagonal(rank_correlation.values, 1.0)
    eigenvalues = np.clip(
        np.linalg.eigvalsh(rank_correlation.to_numpy(dtype=float)), 0.0, None
    )
    effective_rank = float(eigenvalues.sum() ** 2 / np.square(eigenvalues).sum())

    correlation = numeric[usable].corr(method="spearman", min_periods=100).fillna(0.0)
    np.fill_diagonal(correlation.values, 1.0)
    eligible_pairs = [
        (left, right)
        for left_index, left in enumerate(usable)
        for right in usable[left_index + 1 :]
        if reference_features is None or left in added or right in added
    ]
    if eligible_pairs:
        pair = max(
            eligible_pairs,
            key=lambda names: abs(correlation.loc[names[0], names[1]]),
        )
        maximum = float(abs(correlation.loc[pair[0], pair[1]]))
    else:
        pair, maximum = (), float("nan")
    return {
        "usable_feature_count": len(usable),
        "effective_rank_feature_count": len(rank_scope),
        "effective_rank_scope": "added_features" if reference_features is not None else "all_features",
        "effective_rank": effective_rank,
        "effective_rank_fraction": effective_rank / len(rank_scope),
        "maximum_absolute_spearman": maximum,
        "maximum_correlation_pair": list(pair),
    }


def load_oof_prediction(run: str | Path) -> pd.DataFrame:
    path = Path(run) / "predictions" / "oof_predictions.parquet"
    frame = pd.read_parquet(path)
    required = {
        "fold_id",
        "symbol",
        "date",
        "y_entry",
        "sample_weight",
        "p_entry_raw",
        "p_entry_calibrated_temporal",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"OOF prediction is missing columns: {missing}")
    frame["date"] = pd.to_datetime(frame["date"], errors="raise").dt.normalize()
    if frame.duplicated(["fold_id", "symbol", "date"]).any():
        raise ValueError(f"OOF prediction contains duplicate keys: {path}")
    return frame


def paired_metrics(
    frame: pd.DataFrame,
    ranking_probability: str = "p_entry_raw",
    calibration_probability: str = "p_entry_calibrated_temporal",
) -> dict[str, float]:
    y = frame["y_entry"].to_numpy(dtype=int)
    p = frame[ranking_probability].to_numpy(dtype=float)
    w = frame["sample_weight"].to_numpy(dtype=float)
    calibrated = frame[calibration_probability].notna().to_numpy()
    calibration_y = y[calibrated]
    calibration_p = frame.loc[calibrated, calibration_probability].to_numpy(dtype=float)
    calibration_w = w[calibrated]
    top5 = daily_topk_metrics(frame, ranking_probability, top_k=5)
    brier = (
        float(brier_score_loss(calibration_y, calibration_p, sample_weight=calibration_w))
        if calibrated.any()
        else float("nan")
    )
    ece = (
        expected_calibration_error(calibration_y, calibration_p, calibration_w)
        if calibrated.any()
        else float("nan")
    )
    return {
        "rows": int(len(frame)),
        "positive_rate": float(np.average(y, weights=w)),
        "roc_auc": float(roc_auc_score(y, p, sample_weight=w)),
        "average_precision": float(average_precision_score(y, p, sample_weight=w)),
        "temporal_calibration_rows": int(calibrated.sum()),
        "brier_score_temporal": brier,
        "ece_10_temporal": ece,
        **top5,
    }


def daily_topk_metrics(frame: pd.DataFrame, probability_column: str, top_k: int) -> dict[str, float]:
    ranked = frame.sort_values(
        ["date", probability_column, "symbol"],
        ascending=[True, False, True],
        kind="stable",
    )
    selected = ranked.groupby("date", sort=False, group_keys=False).head(top_k)
    precision = float(np.average(selected["y_entry"], weights=selected["sample_weight"]))
    base_rate = float(np.average(frame["y_entry"], weights=frame["sample_weight"]))
    return {
        f"daily_precision_at_{top_k}": precision,
        f"daily_lift_at_{top_k}": precision / base_rate if base_rate > 0 else float("nan"),
    }


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
        observed = float(np.average(y_true[mask], weights=weight[mask]))
        predicted = float(np.average(probability[mask], weights=weight[mask]))
        error += float(weight[mask].sum()) / total * abs(observed - predicted)
    return float(error)


def compare_paired(base: pd.DataFrame, candidate: pd.DataFrame) -> tuple[dict[str, Any], pd.DataFrame]:
    keys = ["fold_id", "symbol", "date"]
    prediction_columns = ["p_entry_raw", "p_entry_calibrated_temporal"]
    candidate = candidate[keys + ["y_entry", "sample_weight", *prediction_columns]].rename(
        columns={column: f"{column}_candidate" for column in ["y_entry", "sample_weight", *prediction_columns]}
    )
    base = base[keys + ["y_entry", "sample_weight", *prediction_columns]].rename(
        columns={column: f"{column}_base" for column in ["y_entry", "sample_weight", *prediction_columns]}
    )
    paired = base.merge(candidate, on=keys, how="inner", validate="one_to_one")
    if paired.empty:
        raise ValueError("Base and candidate OOF tables have no paired rows.")
    if not (paired["y_entry_base"] == paired["y_entry_candidate"]).all():
        raise ValueError("Base and candidate targets differ on paired rows.")
    if not np.allclose(
        paired["sample_weight_base"], paired["sample_weight_candidate"], equal_nan=True
    ):
        raise ValueError("Base and candidate sample weights differ on paired rows.")
    if len(paired) != len(base) or len(paired) != len(candidate):
        raise ValueError("Base and candidate OOF key coverage differs.")
    paired["y_entry"] = paired["y_entry_base"]
    paired["sample_weight"] = paired["sample_weight_base"]
    base_metrics = paired_metrics(
        paired.rename(
            columns={
                "p_entry_raw_base": "p_entry_raw",
                "p_entry_calibrated_temporal_base": "p_entry_calibrated_temporal",
            }
        )
    )
    candidate_metrics = paired_metrics(
        paired.rename(
            columns={
                "p_entry_raw_candidate": "p_entry_raw",
                "p_entry_calibrated_temporal_candidate": "p_entry_calibrated_temporal",
            }
        )
    )
    fold_rows: list[dict[str, Any]] = []
    for fold_id, group in paired.groupby("fold_id", sort=True):
        fold_base = paired_metrics(
            group.rename(columns={"p_entry_raw_base": "p_entry_raw", "p_entry_calibrated_temporal_base": "p_entry_calibrated_temporal"})
        )
        fold_candidate = paired_metrics(
            group.rename(columns={"p_entry_raw_candidate": "p_entry_raw", "p_entry_calibrated_temporal_candidate": "p_entry_calibrated_temporal"})
        )
        fold_rows.append(
            {
                "fold_id": fold_id,
                "rows": fold_base["rows"],
                "base_average_precision": fold_base["average_precision"],
                "candidate_average_precision": fold_candidate["average_precision"],
                "delta_average_precision": fold_candidate["average_precision"] - fold_base["average_precision"],
                "base_roc_auc": fold_base["roc_auc"],
                "candidate_roc_auc": fold_candidate["roc_auc"],
                "delta_roc_auc": fold_candidate["roc_auc"] - fold_base["roc_auc"],
                "delta_daily_precision_at_5": fold_candidate["daily_precision_at_5"]
                - fold_base["daily_precision_at_5"],
            }
        )
    summary = {
        "paired_rows": int(len(paired)),
        "base": base_metrics,
        "candidate": candidate_metrics,
        "delta_average_precision": candidate_metrics["average_precision"] - base_metrics["average_precision"],
        "delta_roc_auc": candidate_metrics["roc_auc"] - base_metrics["roc_auc"],
        "delta_ece_10_temporal": candidate_metrics["ece_10_temporal"]
        - base_metrics["ece_10_temporal"],
        "daily_precision_at_5_relative_gain": (
            candidate_metrics["daily_precision_at_5"] / base_metrics["daily_precision_at_5"] - 1.0
        ),
        "positive_fold_count_ap": int(sum(row["delta_average_precision"] >= 0 for row in fold_rows)),
    }
    return summary, pd.DataFrame(fold_rows)
