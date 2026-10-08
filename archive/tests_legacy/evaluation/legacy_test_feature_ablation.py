import numpy as np
import pandas as pd
import pytest

from src.evaluation.feature_ablation import compare_paired, feature_redundancy_metrics


def test_paired_ablation_rejects_key_coverage_mismatch():
    base = pd.DataFrame(
        {
            "fold_id": ["fold_2020", "fold_2021", "fold_2021"],
            "symbol": ["AAA", "AAA", "BBB"],
            "date": pd.to_datetime(["2020-01-01", "2021-01-01", "2021-01-01"]),
            "y_entry": [0, 1, 0],
            "sample_weight": [1.0, 1.0, 1.0],
            "p_entry_raw": [0.1, 0.8, 0.2],
            "p_entry_calibrated_temporal": [0.1, 0.8, 0.2],
        }
    )
    candidate = base.iloc[[1, 2]].copy()
    candidate["p_entry_raw"] = [0.9, 0.1]
    candidate["p_entry_calibrated_temporal"] = [0.9, 0.1]
    try:
        compare_paired(base, candidate)
    except ValueError as error:
        assert "key coverage differs" in str(error)
    else:
        raise AssertionError("Mismatched OOF coverage must be rejected")


def test_paired_ablation_rejects_weight_mismatch():
    base = pd.DataFrame(
        {
            "fold_id": ["fold_2021", "fold_2021"],
            "symbol": ["AAA", "BBB"],
            "date": pd.to_datetime(["2021-01-01", "2021-01-01"]),
            "y_entry": [1, 0],
            "sample_weight": [1.0, 1.0],
            "p_entry_raw": [0.8, 0.2],
            "p_entry_calibrated_temporal": [0.7, 0.1],
        }
    )
    candidate = base.copy()
    candidate.loc[0, "sample_weight"] = 0.5
    try:
        compare_paired(base, candidate)
    except ValueError as error:
        assert "sample weights differ" in str(error)
    else:
        raise AssertionError("Mismatched sample weights must be rejected")


def test_feature_redundancy_focuses_on_added_features():
    frame = pd.DataFrame(
        {
            "base_a": range(200),
            "base_b": range(200),
            "added": range(200),
            "independent": np.random.default_rng(238).normal(size=200),
        }
    )
    metrics = feature_redundancy_metrics(
        frame,
        reference_features={"base_a", "base_b"},
    )
    assert metrics["maximum_absolute_spearman"] == pytest.approx(1.0)
    assert "added" in metrics["maximum_correlation_pair"]
    assert 0 < metrics["effective_rank_fraction"] < 1
