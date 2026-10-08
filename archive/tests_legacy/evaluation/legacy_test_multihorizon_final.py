import numpy as np
import pandas as pd
import pytest

from src.evaluation.multihorizon_final import (
    compare_causal_oof_combiners,
    evaluate_frozen_combiner,
    join_final_predictions,
)


def make_frame(horizon: str, rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows).rename(columns={"probability": f"p_{horizon}"})


def test_final_join_requires_all_horizons_to_cover_h120_rows():
    common = [
        {"symbol": "AAA", "date": pd.Timestamp("2025-01-02"), "y_entry": 0, "sample_weight": 1.0, "probability": 0.2},
        {"symbol": "BBB", "date": pd.Timestamp("2025-01-02"), "y_entry": 1, "sample_weight": 1.0, "probability": 0.8},
    ]
    frames = {name: make_frame(name, common) for name in ("h20", "h60", "h120")}
    frames["h20"] = frames["h20"].iloc[:1]
    with pytest.raises(ValueError, match="Complete coverage"):
        join_final_predictions(frames)


def test_final_metrics_use_frozen_threshold_and_stable_top_k():
    rows = [
        {"symbol": "BBB", "date": pd.Timestamp("2025-01-02"), "y_entry": 0, "sample_weight": 1.0, "probability": 0.5},
        {"symbol": "AAA", "date": pd.Timestamp("2025-01-02"), "y_entry": 1, "sample_weight": 1.0, "probability": 0.5},
        {"symbol": "CCC", "date": pd.Timestamp("2025-01-03"), "y_entry": 1, "sample_weight": 1.0, "probability": 0.9},
        {"symbol": "DDD", "date": pd.Timestamp("2025-01-03"), "y_entry": 0, "sample_weight": 1.0, "probability": 0.1},
    ]
    frame, coverage = join_final_predictions({name: make_frame(name, rows) for name in ("h20", "h60", "h120")})
    metrics, predictions = evaluate_frozen_combiner(
        frame,
        probability=np.array([0.5, 0.5, 0.9, 0.1]),
        threshold=0.75,
        top_k=1,
    )
    assert metrics["decision_threshold_from_causal_oof"] == 0.75
    assert coverage["evaluation_rows"] == 4
    assert predictions.loc[predictions["symbol"].eq("AAA"), "selected_top_k_meta"].item()
    assert not predictions.loc[predictions["symbol"].eq("BBB"), "selected_top_k_meta"].item()
    assert metrics["combiner"]["recall"] == 0.5


def test_candidate_comparison_uses_only_common_oof_rows():
    rows = [
        {
            "symbol": "AAA",
            "date": pd.Timestamp("2025-01-02"),
            "y_entry_h120": 0,
            "sample_weight_h120": 1.0,
            "p_h120": 0.1,
            "p_meta": 0.1,
        },
        {
            "symbol": "BBB",
            "date": pd.Timestamp("2025-01-02"),
            "y_entry_h120": 1,
            "sample_weight_h120": 1.0,
            "p_h120": 0.7,
            "p_meta": 0.8,
        },
        {
            "symbol": "CCC",
            "date": pd.Timestamp("2025-01-03"),
            "y_entry_h120": 1,
            "sample_weight_h120": 1.0,
            "p_h120": 0.6,
            "p_meta": 0.7,
        },
    ]
    legacy = pd.DataFrame(rows)
    candidate = pd.DataFrame(
        rows
        + [
            {
                "symbol": "DDD",
                "date": pd.Timestamp("2025-01-03"),
                "y_entry_h120": 0,
                "sample_weight_h120": 1.0,
                "p_h120": 0.2,
                "p_meta": 0.2,
            }
        ]
    )
    report = compare_causal_oof_combiners(legacy, candidate, legacy_threshold=0.5, candidate_threshold=0.5, top_k=1)
    assert report["comparison_rows"] == 3
    assert report["candidate_scored_rows"] == 4
