from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.training.h120_experiment_protocol import H120ExperimentProtocol

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = ROOT / "configs/experiments/h120_ranker_generation_v2.yaml"


def test_generation_v2_locks_stock_only_binary_h120_contract() -> None:
    protocol = H120ExperimentProtocol.from_yaml(PROTOCOL_PATH)

    features = protocol.validate_feature_group(
        ROOT / "reports/h120_improvement/feature_governance/feature_groups_resolved.json"
    )
    protocol.validate_label_config(
        ROOT / "configs/wave_continuation_labels_h120_v3_eventweights.yaml"
    )

    assert len(features) == 50
    assert protocol.selection_folds == (
        "fold_2020", "fold_2021", "fold_2022", "fold_2023"
    )
    assert protocol.confirmation_seeds == (238, 239, 240, 241, 242)


def test_generation_v2_rejects_fold_2024_from_selection() -> None:
    protocol = H120ExperimentProtocol.from_yaml(PROTOCOL_PATH)

    with pytest.raises(ValueError, match="frozen inner folds"):
        protocol.validate_selection_folds(
            ["fold_2020", "fold_2021", "fold_2022", "fold_2024"]
        )


def test_future_holdout_is_registered_and_sealed() -> None:
    registration = json.loads(
        (ROOT / "experiments/h120_improvement/E10_future_holdout/registration.json").read_text(
            encoding="utf-8"
        )
    )

    assert registration["protocol"] == "configs/experiments/h120_ranker_generation_v2.yaml"
    assert registration["outcome_access"] == "sealed"
    assert registration["selection_allowed"] is False
    assert registration["training_allowed"] is False
    assert "fold_2024" in registration["excluded_from_selection"]
