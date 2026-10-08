"""End-to-end metrics for the V6 cascade."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)


def daily_top_k_precision(
    frame: pd.DataFrame,
    probability_column: str = "p_cascade",
    target_column: str = "y_actionable",
    weight_column: str = "sample_weight",
    k: int = 5,
    candidate_mask: pd.Series | np.ndarray | None = None,
) -> dict[str, float]:
    required = {"date", probability_column, target_column, weight_column}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Top-K frame is missing: {missing}")
    working = frame.copy()
    working[probability_column] = pd.to_numeric(working[probability_column], errors="coerce")
    working[weight_column] = pd.to_numeric(working[weight_column], errors="coerce")
    working = working.loc[working[probability_column].notna() & working[weight_column].notna()].copy()
    if candidate_mask is not None:
        mask = pd.Series(candidate_mask, index=working.index).astype(bool)
        working = working.loc[mask].copy()
    selected: list[pd.DataFrame] = []
    sort_columns = ["date", probability_column]
    ascending = [True, False]
    if "symbol" in working.columns:
        sort_columns.append("symbol")
        ascending.append(True)
    for _, group in working.sort_values(
        sort_columns, ascending=ascending, kind="stable"
    ).groupby("date", sort=False):
        selected.append(group.head(k))
    if not selected:
        return {
            "selected_rows": 0.0,
            "selected_days": 0.0,
            "average_recommendations_per_day": 0.0,
            "event_weighted_precision": np.nan,
            "base_rate": np.nan,
            "lift": np.nan,
            "selected_resolved_rows": 0.0,
            "selected_unknown_rows": 0.0,
            "selected_unknown_rate": np.nan,
        }
    top = pd.concat(selected, ignore_index=True)
    top_resolved = top[target_column].notna()
    working_resolved = working[target_column].notna()
    selected_weights = top.loc[top_resolved, weight_column].to_numpy(float)
    selected_values = top.loc[top_resolved, target_column].to_numpy(float)
    resolved_weights = working.loc[working_resolved, weight_column].to_numpy(float)
    resolved_values = working.loc[working_resolved, target_column].to_numpy(float)
    selected_weight_sum = float(selected_weights.sum())
    resolved_weight_sum = float(resolved_weights.sum())
    precision = (
        float(np.average(selected_values, weights=selected_weights))
        if selected_weight_sum > 0
        else np.nan
    )
    base = (
        float(np.average(resolved_values, weights=resolved_weights))
        if resolved_weight_sum > 0
        else np.nan
    )
    unknown_rows = int((~top_resolved).sum())
    return {
        "selected_rows": float(len(top)),
        "selected_days": float(top["date"].nunique()),
        "average_recommendations_per_day": float(len(top) / top["date"].nunique()),
        "event_weighted_precision": float(precision),
        "base_rate": float(base),
        "lift": float(precision / base) if base > 0 else np.nan,
        "selected_resolved_rows": float(top_resolved.sum()),
        "selected_unknown_rows": float(unknown_rows),
        "selected_unknown_rate": float(unknown_rows / len(top)) if len(top) else np.nan,
    }


def daily_candidate_pool_mask(
    frame: pd.DataFrame,
    probability_column: str = "p_h20",
    candidate_k: int = 50,
) -> pd.Series:
    """Select a deterministic per-day candidate pool from an upstream head."""

    required = {"date", "symbol", probability_column}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Candidate-pool frame is missing: {missing}")
    if candidate_k <= 0:
        raise ValueError("candidate_k must be positive.")
    finite = pd.to_numeric(frame[probability_column], errors="coerce").notna()
    ordered = frame.loc[finite].sort_values(
        ["date", probability_column, "symbol"],
        ascending=[True, False, True],
        kind="stable",
    )
    rank = ordered.groupby("date", observed=True).cumcount().add(1)
    selected = pd.Series(False, index=frame.index, dtype=bool)
    selected.loc[rank.index] = rank.le(candidate_k).to_numpy(dtype=bool)
    return selected


def add_strength_ranking_score(
    frame: pd.DataFrame,
    *,
    probability_column: str = "p_cascade",
    strength_columns: tuple[str, ...] = ("strength_h60", "strength_h120"),
    strength_weight: float = 0.25,
    output_column: str = "p_rank",
) -> pd.DataFrame:
    """Apply strength only as a post-cascade ranking adjustment.

    Strength is centered at 0.5, so missing strength is neutral and cannot
    create a false probability improvement.  The base cascade probability is
    preserved for calibration metrics; only ``output_column`` is used for
    shortlist ordering.
    """

    if not 0.0 <= strength_weight <= 1.0:
        raise ValueError("strength_weight must be between 0 and 1.")
    if probability_column not in frame:
        raise ValueError(f"Missing probability column: {probability_column}")
    result = frame.copy()
    available = [column for column in strength_columns if column in result]
    if not available:
        result[output_column] = result[probability_column]
        result["strength_rank_score"] = 0.5
        return result
    strength = result[available].apply(pd.to_numeric, errors="coerce").mean(axis=1)
    strength = strength.fillna(0.5).clip(0.0, 1.0)
    result["strength_rank_score"] = strength
    result[output_column] = result[probability_column] * (
        1.0 + strength_weight * (strength - 0.5) * 2.0
    )
    return result


def candidate_pool_metrics(
    frame: pd.DataFrame,
    *,
    candidate_probability_column: str = "p_h20",
    candidate_k: int = 50,
    ranking_probability_column: str = "p_cascade",
    target_column: str = "y_actionable",
    weight_column: str = "sample_weight",
    top_k: int = 10,
) -> dict[str, float]:
    """Measure the production path: upstream pool -> downstream shortlist."""

    required = {
        "date",
        "symbol",
        candidate_probability_column,
        ranking_probability_column,
        target_column,
        weight_column,
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Candidate-pool metrics are missing: {missing}")
    pool_mask = daily_candidate_pool_mask(frame, candidate_probability_column, candidate_k)
    pool = frame.loc[pool_mask].copy()
    total_weight = float(frame[weight_column].sum())
    pool_weight = float(pool[weight_column].sum())
    resolved = frame[target_column].notna()
    pool_resolved = pool[target_column].notna()
    total_positive = float(
        np.sum(
            frame.loc[resolved, target_column].to_numpy(float)
            * frame.loc[resolved, weight_column].to_numpy(float)
        )
    )
    pool_positive = float(
        np.sum(
            pool.loc[pool_resolved, target_column].to_numpy(float)
            * pool.loc[pool_resolved, weight_column].to_numpy(float)
        )
    )
    total_resolved_weight = float(frame.loc[resolved, weight_column].sum())
    pool_resolved_weight = float(pool.loc[pool_resolved, weight_column].sum())
    top_k_metrics = daily_top_k_precision(
        frame,
        probability_column=ranking_probability_column,
        target_column=target_column,
        weight_column=weight_column,
        k=top_k,
        candidate_mask=pool_mask,
    )
    return {
        "candidate_k": float(candidate_k),
        "shortlist_k": float(top_k),
        "candidate_rows": float(len(pool)),
        "candidate_days": float(pool["date"].nunique()),
        "candidate_fraction": float(pool_weight / total_weight) if total_weight else np.nan,
        "candidate_positive_rate": float(pool_positive / pool_resolved_weight)
        if pool_resolved_weight
        else np.nan,
        "candidate_recall": float(pool_positive / total_positive) if total_positive else np.nan,
        "candidate_resolved_rows": float(pool_resolved.sum()),
        "candidate_unknown_rows": float((~pool_resolved).sum()),
        "candidate_unknown_rate": float((~pool_resolved).mean()) if len(pool) else np.nan,
        "shortlist_precision": top_k_metrics["event_weighted_precision"],
        "shortlist_lift_vs_full_universe": float(
            top_k_metrics["lift"]
            * (pool_positive / pool_resolved_weight)
            / (total_positive / total_resolved_weight)
        )
        if total_resolved_weight and pool_resolved_weight and total_positive
        else np.nan,
    }


def cascade_metrics(
    frame: pd.DataFrame,
    *,
    probability_column: str = "p_cascade",
    target_column: str = "y_actionable",
    weight_column: str = "sample_weight",
    threshold: float,
    top_k: int = 5,
    candidate_probability_column: str | None = None,
    candidate_k: int = 50,
    ranking_probability_column: str | None = None,
) -> dict[str, object]:
    required = {probability_column, target_column, weight_column}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Cascade frame is missing: {missing}")
    scored_valid = frame[[probability_column, weight_column]].notna().all(axis=1)
    scored = frame.loc[scored_valid].copy()
    metric_rows = scored.loc[scored[target_column].notna()].copy()
    y = metric_rows[target_column].to_numpy(int)
    p = metric_rows[probability_column].to_numpy(float)
    w = metric_rows[weight_column].to_numpy(float)
    predicted = p >= threshold
    has_two_classes = np.unique(y).size >= 2
    result: dict[str, object] = {
        "rows": int(len(metric_rows)),
        "scored_rows": int(len(scored)),
        "unresolved_target_rows": int(len(scored) - len(metric_rows)),
        "days": int(scored["date"].nunique()) if "date" in scored else None,
        "positive_rate": float(np.average(y, weights=w)) if len(metric_rows) else np.nan,
        "roc_auc": float(roc_auc_score(y, p, sample_weight=w)) if has_two_classes else np.nan,
        "average_precision": float(average_precision_score(y, p, sample_weight=w))
        if len(metric_rows)
        else np.nan,
        "brier_score": float(brier_score_loss(y, p, sample_weight=w)) if len(metric_rows) else np.nan,
        "threshold": float(threshold),
        "precision": float(precision_score(y, predicted, sample_weight=w, zero_division=0))
        if len(metric_rows)
        else np.nan,
        "recall": float(recall_score(y, predicted, sample_weight=w, zero_division=0))
        if len(metric_rows)
        else np.nan,
        "f1": float(f1_score(y, predicted, sample_weight=w, zero_division=0))
        if len(metric_rows)
        else np.nan,
    }
    ranking_column = ranking_probability_column or probability_column
    if ranking_column not in scored:
        raise ValueError(f"Ranking probability column is missing: {ranking_column}")
    if "date" in scored:
        result["top_k"] = daily_top_k_precision(
            scored,
            probability_column=ranking_column,
            target_column=target_column,
            weight_column=weight_column,
            k=top_k,
        )
    if candidate_probability_column is not None:
        result["candidate_pool"] = candidate_pool_metrics(
            scored,
            candidate_probability_column=candidate_probability_column,
            candidate_k=candidate_k,
            ranking_probability_column=ranking_column,
            target_column=target_column,
            weight_column=weight_column,
            top_k=top_k,
        )
    return result
