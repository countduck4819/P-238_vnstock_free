from __future__ import annotations

import pandas as pd
import pytest

from src.training.h120_classifier import attach_v3_label_weights


def test_attach_v3_label_weights_is_a_target_preserving_weight_only_change() -> None:
    dataset = pd.DataFrame(
        {
            "symbol": ["AAA", "BBB"],
            "date": pd.to_datetime(["2024-01-02", "2024-01-02"]),
            "y_entry": [0, 1],
            "sample_weight": [1.0, 1.0],
        }
    )
    labels = dataset.loc[:, ["symbol", "date", "y_entry"]].assign(
        event_uniqueness_weight=[0.5, 2.0]
    )

    baseline, baseline_audit = attach_v3_label_weights(dataset, labels, policy="baseline")
    unique, unique_audit = attach_v3_label_weights(dataset, labels, policy="uniqueness")

    assert baseline["sample_weight"].tolist() == [1.0, 1.0]
    assert unique["sample_weight"].tolist() == [0.5, 2.0]
    assert baseline_audit["effective_sample_size"] == pytest.approx(2.0)
    assert unique_audit["effective_sample_size"] == pytest.approx(1.4705882353)


def test_attach_v3_label_weights_rejects_target_change() -> None:
    dataset = pd.DataFrame(
        {
            "symbol": ["AAA"],
            "date": pd.to_datetime(["2024-01-02"]),
            "y_entry": [0],
            "sample_weight": [1.0],
        }
    )
    labels = dataset.assign(y_entry=1, event_uniqueness_weight=1.0)

    with pytest.raises(RuntimeError, match="change y_entry"):
        attach_v3_label_weights(dataset, labels, policy="uniqueness")
