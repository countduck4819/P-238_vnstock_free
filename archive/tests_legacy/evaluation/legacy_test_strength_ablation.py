import pandas as pd
import pytest

from src.evaluation.strength_ablation import compare_strength_paired


def frame(prediction: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "fold_id": ["fold_2021"] * 4,
            "symbol": ["A", "B", "C", "D"],
            "date": pd.to_datetime(["2021-01-01"] * 4),
            "y_entry": [1, 1, 0, 1],
            "y_strength": [0.2, 0.8, None, 0.5],
            "sample_weight": [1.0] * 4,
            "p_strength": prediction,
        }
    )


def test_strength_comparison_requires_identical_targets_and_weights():
    base = frame([0.3, 0.6, 0.1, 0.4])
    candidate = frame([0.2, 0.8, 0.1, 0.5])
    summary, folds = compare_strength_paired(base, candidate)
    assert summary["candidate"]["weighted_mae"] < summary["baseline"]["weighted_mae"]
    assert folds.loc[0, "delta_weighted_mae"] < 0

    candidate.loc[0, "sample_weight"] = 2.0
    with pytest.raises(ValueError, match="sample_weight"):
        compare_strength_paired(base, candidate)
