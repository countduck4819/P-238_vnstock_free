import pandas as pd

from scripts.build_h120_cascade_frame import align_prediction
from src.evaluation.wave_cascade import (
    add_strength_ranking_score,
    candidate_pool_metrics,
    cascade_metrics,
    daily_candidate_pool_mask,
    daily_top_k_precision,
)


def test_prediction_alignment_is_causal_and_records_lag() -> None:
    anchor = pd.DataFrame(
        {
            "symbol": ["AAA", "AAA", "BBB"],
            "date": pd.to_datetime(["2025-01-03", "2025-01-05", "2025-01-08"]),
        }
    )
    source = pd.DataFrame(
        {
            "symbol": ["AAA", "AAA", "BBB"],
            "date": pd.to_datetime(["2025-01-01", "2025-01-10", "2025-01-01"]),
            "p_v6_trend": [0.7, 0.9, 0.4],
        }
    )

    aligned = align_prediction(
        anchor,
        source,
        value_column="p_v6_trend",
        name="v6_trend",
        mode="asof",
        max_lag_days=5,
    )

    assert aligned["p_v6_trend"].tolist()[:2] == [0.7, 0.7]
    assert pd.isna(aligned.loc[2, "p_v6_trend"])
    assert aligned["p_v6_trend_source_date"].dt.strftime("%Y-%m-%d").tolist()[:2] == [
        "2025-01-01",
        "2025-01-01",
    ]
    assert aligned["p_v6_trend_lag_days"].iloc[:2].tolist() == [2.0, 4.0]
    assert pd.isna(aligned.loc[2, "p_v6_trend_lag_days"])


def test_cascade_metrics_reports_top_k_lift() -> None:
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-01"] * 4 + ["2025-01-02"] * 4),
            "p_cascade": [0.9, 0.8, 0.2, 0.1, 0.95, 0.4, 0.3, 0.2],
            "y_actionable": [1, 0, 0, 0, 1, 1, 0, 0],
            "sample_weight": [1.0] * 8,
        }
    )
    metrics = cascade_metrics(frame, threshold=0.5, top_k=1)
    assert metrics["rows"] == 8
    assert metrics["top_k"]["selected_rows"] == 2.0
    assert metrics["top_k"]["event_weighted_precision"] == 1.0
    assert metrics["top_k"]["lift"] > 1.0


def test_daily_top_k_is_deterministic() -> None:
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-01"] * 2),
            "symbol": ["BBB", "AAA"],
            "p_cascade": [0.5, 0.5],
            "y_actionable": [0, 1],
            "sample_weight": [1.0, 1.0],
        }
    )
    result = daily_top_k_precision(frame, k=1)
    assert result["selected_rows"] == 1.0


def test_candidate_pool_metrics_selects_downstream_top_k_inside_upstream_pool() -> None:
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-01"] * 4),
            "symbol": ["AAA", "BBB", "CCC", "DDD"],
            "p_h20": [0.90, 0.80, 0.70, 0.10],
            "p_cascade": [0.20, 0.95, 0.90, 0.99],
            "y_actionable": [1, 1, 0, 1],
            "sample_weight": [1.0] * 4,
        }
    )
    mask = daily_candidate_pool_mask(frame, probability_column="p_h20", candidate_k=2)
    assert mask.tolist() == [True, True, False, False]
    result = candidate_pool_metrics(
        frame, candidate_probability_column="p_h20", candidate_k=2, top_k=1
    )
    assert result["candidate_rows"] == 2.0
    assert result["candidate_recall"] == 2.0 / 3.0
    assert result["shortlist_precision"] == 1.0


def test_strength_is_a_neutral_post_ranking_adjustment_when_missing() -> None:
    frame = pd.DataFrame({"p_cascade": [0.4, 0.6], "strength_h60": [1.0, None]})
    ranked = add_strength_ranking_score(
        frame,
        strength_columns=("strength_h60",),
        strength_weight=0.25,
    )
    assert ranked.loc[0, "p_rank"] > frame.loc[0, "p_cascade"]
    assert ranked.loc[1, "p_rank"] == frame.loc[1, "p_cascade"]


def test_top_k_ranks_unknown_targets_but_scores_only_resolved_rows() -> None:
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-01"] * 3),
            "symbol": ["AAA", "BBB", "CCC"],
            "p_cascade": [0.99, 0.80, 0.10],
            "y_actionable": [pd.NA, 1, 0],
            "sample_weight": [1.0, 1.0, 1.0],
        }
    )
    result = cascade_metrics(frame, threshold=0.5, top_k=1)
    assert result["rows"] == 2
    assert result["scored_rows"] == 3
    assert result["unresolved_target_rows"] == 1
    assert result["top_k"]["selected_unknown_rows"] == 1.0
    assert pd.isna(result["top_k"]["event_weighted_precision"])
