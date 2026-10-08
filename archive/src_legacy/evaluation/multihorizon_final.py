"""Final-holdout reporting for a frozen multi-horizon combiner.

This module deliberately has no fitting or threshold-selection functions.  The
combiner and its threshold must already have been fitted from causal OOF data;
this layer only joins immutable final-test predictions and reports what they
achieved on the H120 target.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    f1_score,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)

FINAL_COLUMNS = {
    "symbol",
    "date",
    "y_entry",
    "sample_weight",
    "p_entry_calibrated",
}
KEY_COLUMNS = ["symbol", "date"]


def load_final_prediction(path: str, horizon: str) -> pd.DataFrame:
    """Load one final-test prediction table with a namespaced probability."""
    frame = pd.read_parquet(path)
    missing = sorted(FINAL_COLUMNS - set(frame.columns))
    if missing:
        raise ValueError(f"{horizon} final predictions are missing columns: {missing}")
    result = frame.loc[:, [*KEY_COLUMNS, "y_entry", "sample_weight", "p_entry_calibrated"]].copy()
    result["date"] = pd.to_datetime(result["date"], errors="raise").dt.normalize()
    if result.duplicated(KEY_COLUMNS).any():
        raise ValueError(f"{horizon} final predictions contain duplicate symbol/date keys.")
    if result["p_entry_calibrated"].isna().any():
        raise ValueError(f"{horizon} final predictions contain missing probabilities.")
    if (result["sample_weight"] <= 0).any() or result["sample_weight"].isna().any():
        raise ValueError(f"{horizon} final predictions have invalid sample weights.")
    return result.rename(columns={"p_entry_calibrated": f"p_{horizon}"})


def join_final_predictions(
    frames: dict[str, pd.DataFrame], *, coverage_policy: str = "complete"
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Join resolved H120 rows under an explicit horizon-coverage policy."""
    required_horizons = {"h20", "h60", "h120"}
    missing = sorted(required_horizons - set(frames))
    if missing:
        raise ValueError(f"Missing final-test horizons: {missing}")
    if coverage_policy not in {"complete", "intersection", "missing_aware"}:
        raise ValueError("coverage_policy must be complete, intersection, or missing_aware.")
    target = frames["h120"].rename(columns={"y_entry": "y_entry_h120", "sample_weight": "sample_weight_h120"})
    result = target
    target_keys = target.loc[:, KEY_COLUMNS]
    coverage: dict[str, Any] = {
        "policy": coverage_policy,
        "h120_resolved_rows": int(len(target)),
        "h120_resolved_days": int(target["date"].nunique()),
        "horizon_coverage": {},
    }
    for horizon in ("h20", "h60"):
        source = frames[horizon]
        key_coverage = target_keys.merge(source.loc[:, KEY_COLUMNS], on=KEY_COLUMNS, how="left", indicator=True)
        matched_rows = int(key_coverage["_merge"].eq("both").sum())
        coverage["horizon_coverage"][horizon] = {
            "matched_rows": matched_rows,
            "missing_rows": int(len(key_coverage) - matched_rows),
            "matched_fraction": float(matched_rows / len(key_coverage)),
        }
        result = result.merge(
            source.loc[:, [*KEY_COLUMNS, f"p_{horizon}"]],
            on=KEY_COLUMNS,
            how="left",
            validate="one_to_one",
        )
    probability_columns = ["p_h20", "p_h60", "p_h120"]
    if coverage_policy == "complete" and result[probability_columns].isna().any().any():
        missing_rows = int(result[probability_columns].isna().any(axis=1).sum())
        raise ValueError(f"Complete coverage requires all horizons; {missing_rows} H120 rows are incomplete.")
    if coverage_policy == "intersection":
        result = result.dropna(subset=probability_columns).copy()
    if coverage_policy == "missing_aware" and result["p_h120"].isna().any():
        raise RuntimeError("The target H120 probability must cover every resolved H120 row.")
    if result["y_entry_h120"].nunique() < 2:
        raise ValueError("Resolved final H120 rows must contain both target classes.")
    result = result.sort_values(["date", "symbol"], kind="stable").reset_index(drop=True)
    coverage["evaluation_rows"] = int(len(result))
    coverage["evaluation_days"] = int(result["date"].nunique())
    coverage["evaluation_fraction_of_h120"] = float(len(result) / len(target))
    return result, coverage


def evaluate_frozen_combiner(
    frame: pd.DataFrame,
    *,
    probability: np.ndarray,
    threshold: float,
    top_k: int,
) -> tuple[dict[str, Any], pd.DataFrame]:
    """Report combiner quality with an OOF-frozen threshold, never optimizing it."""
    if not 0.0 < threshold < 1.0:
        raise ValueError("Frozen decision threshold must be in (0, 1).")
    if top_k <= 0:
        raise ValueError("top_k must be positive.")
    if len(frame) != len(probability):
        raise ValueError("Probability count does not match final-test rows.")
    result = frame.copy()
    result["p_meta"] = np.asarray(probability, dtype=float)
    valid_probability_range = bool(result["p_meta"].between(0.0, 1.0).all())
    if not np.isfinite(result["p_meta"]).all() or not valid_probability_range:
        raise ValueError("Combiner returned invalid probabilities.")
    result["predicted_entry"] = result["p_meta"].ge(threshold).astype("int8")
    result["daily_rank_meta"] = _daily_rank(result, "p_meta")
    result["daily_rank_h120"] = _daily_rank(result, "p_h120")
    result["selected_top_k_meta"] = result["daily_rank_meta"].le(top_k)
    result["selected_top_k_h120"] = result["daily_rank_h120"].le(top_k)

    y = result["y_entry_h120"].to_numpy(dtype=int)
    weight = result["sample_weight_h120"].to_numpy(dtype=float)
    metrics = {
        "target": "h120_continuation",
        "decision_threshold_from_causal_oof": float(threshold),
        "rows": int(len(result)),
        "days": int(result["date"].nunique()),
        "positive_rate": float(np.average(y, weights=weight)),
        "combiner": _classification_metrics(y, result["p_meta"].to_numpy(dtype=float), weight, threshold),
        "h120_baseline_same_rows": _classification_metrics(
            y, result["p_h120"].to_numpy(dtype=float), weight, threshold
        ),
        "top_k": {
            "k": int(top_k),
            "combiner": _top_k_metrics(result, "selected_top_k_meta"),
            "h120_baseline_same_rows": _top_k_metrics(result, "selected_top_k_h120"),
        },
    }
    metrics["top_k"]["combiner"]["lift_vs_h120_baseline"] = _relative_gain(
        metrics["top_k"]["combiner"]["event_weighted_precision"],
        metrics["top_k"]["h120_baseline_same_rows"]["event_weighted_precision"],
    )
    return metrics, result


def compare_causal_oof_combiners(
    legacy: pd.DataFrame,
    candidate: pd.DataFrame,
    *,
    legacy_threshold: float,
    candidate_threshold: float,
    top_k: int,
) -> dict[str, Any]:
    """Compare OOF-only candidates on the exact legacy eligible population."""
    required = {"symbol", "date", "y_entry_h120", "sample_weight_h120", "p_h120", "p_meta"}
    for name, frame in (("legacy", legacy), ("candidate", candidate)):
        missing = sorted(required - set(frame.columns))
        if missing:
            raise ValueError(f"{name} OOF predictions are missing columns: {missing}")
    legacy_rows = legacy.loc[legacy["p_meta"].notna()].copy()
    candidate_rows = candidate.loc[candidate["p_meta"].notna()].copy()
    key_columns = ["symbol", "date"]
    joined = legacy_rows.merge(
        candidate_rows,
        on=key_columns,
        how="inner",
        suffixes=("_legacy", "_candidate"),
        validate="one_to_one",
    )
    if joined.empty:
        raise ValueError("Legacy and candidate OOF predictions have no common scored rows.")
    for column in ("y_entry_h120", "sample_weight_h120"):
        left = joined[f"{column}_legacy"].to_numpy()
        right = joined[f"{column}_candidate"].to_numpy()
        if column == "y_entry_h120":
            equal = np.array_equal(left, right)
        else:
            equal = np.allclose(left, right, equal_nan=False)
        if not equal:
            raise ValueError(f"Legacy and candidate OOF {column} differ on common rows.")
    base = joined.rename(
        columns={
            "y_entry_h120_legacy": "y_entry_h120",
            "sample_weight_h120_legacy": "sample_weight_h120",
            "p_h120_legacy": "p_h120",
        }
    )
    legacy_metrics, _ = evaluate_frozen_combiner(
        base, probability=base["p_meta_legacy"].to_numpy(), threshold=legacy_threshold, top_k=top_k
    )
    candidate_metrics, _ = evaluate_frozen_combiner(
        base, probability=base["p_meta_candidate"].to_numpy(), threshold=candidate_threshold, top_k=top_k
    )
    return {
        "comparison_rows": int(len(base)),
        "comparison_days": int(base["date"].nunique()),
        "legacy_scored_rows": int(len(legacy_rows)),
        "candidate_scored_rows": int(len(candidate_rows)),
        "legacy": legacy_metrics,
        "candidate": candidate_metrics,
        "delta_candidate_minus_legacy": {
            "average_precision": candidate_metrics["combiner"]["average_precision"]
            - legacy_metrics["combiner"]["average_precision"],
            "brier_score": candidate_metrics["combiner"]["brier_score"] - legacy_metrics["combiner"]["brier_score"],
            "top_k_event_weighted_precision": candidate_metrics["top_k"]["combiner"]["event_weighted_precision"]
            - legacy_metrics["top_k"]["combiner"]["event_weighted_precision"],
        },
    }


def _classification_metrics(
    y: np.ndarray, probability: np.ndarray, weight: np.ndarray, threshold: float
) -> dict[str, float]:
    predicted = probability >= threshold
    return {
        "roc_auc": float(roc_auc_score(y, probability, sample_weight=weight)),
        "average_precision": float(average_precision_score(y, probability, sample_weight=weight)),
        "brier_score": float(brier_score_loss(y, probability, sample_weight=weight)),
        "log_loss": float(log_loss(y, probability, sample_weight=weight, labels=[0, 1])),
        "precision": float(precision_score(y, predicted, sample_weight=weight, zero_division=0)),
        "recall": float(recall_score(y, predicted, sample_weight=weight, zero_division=0)),
        "f1": float(f1_score(y, predicted, sample_weight=weight, zero_division=0)),
    }


def _daily_rank(frame: pd.DataFrame, probability_column: str) -> pd.Series:
    ordered = frame.sort_values(["date", probability_column, "symbol"], ascending=[True, False, True], kind="stable")
    ranks = ordered.groupby("date", observed=True).cumcount().add(1).astype("Int64")
    return ranks.reindex(frame.index)


def _top_k_metrics(frame: pd.DataFrame, selected_column: str) -> dict[str, float]:
    selected = frame.loc[frame[selected_column]].copy()
    if selected.empty:
        return {"selected_rows": 0.0, "selected_days": 0.0, "event_weighted_precision": float("nan")}
    selected_weight = selected["sample_weight_h120"].to_numpy(dtype=float)
    precision = float(np.average(selected["y_entry_h120"].to_numpy(dtype=float), weights=selected_weight))
    return {
        "selected_rows": float(len(selected)),
        "selected_days": float(selected["date"].nunique()),
        "event_weighted_precision": precision,
        "selected_weight": float(selected_weight.sum()),
        "average_recommendations_per_selected_day": float(len(selected) / selected["date"].nunique()),
    }


def _relative_gain(value: float, baseline: float) -> float:
    if not np.isfinite(value) or not np.isfinite(baseline) or baseline == 0.0:
        return float("nan")
    return float(value / baseline - 1.0)
