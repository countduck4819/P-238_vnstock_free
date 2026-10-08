from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from archive.scripts_legacy.h20_onset.train_h20_onset_challenger import train_fold
from src.training.xgboost_pipeline import (
    SigmoidCalibration,
    XGBoostTrainingConfig,
    classification_metrics,
    fit_sigmoid_calibration,
    median_best_round,
    regression_metrics,
    select_f1_threshold,
    subset_by_keys,
    temporal_calibration_predictions,
    weighted_class_ratio,
)


def test_weighted_class_ratio_uses_weight_mass_not_row_count() -> None:
    target = np.array([0, 0, 1, 1])
    weights = np.array([1.0, 1.0, 0.25, 0.25])

    assert weighted_class_ratio(target, weights) == pytest.approx(4.0)


def test_sigmoid_calibration_round_trip_and_probability_bounds() -> None:
    probability = np.array([0.02, 0.10, 0.20, 0.70, 0.85, 0.98])
    target = np.array([0, 0, 0, 1, 1, 1])
    weights = np.ones_like(probability)
    fitted = fit_sigmoid_calibration(probability, target, weights)
    restored = SigmoidCalibration.from_dict(fitted.to_dict())

    calibrated = restored.predict(np.array([0.0, 0.5, 1.0]))
    assert np.isfinite(calibrated).all()
    assert ((calibrated > 0) & (calibrated < 1)).all()
    assert np.all(np.diff(calibrated) > 0)


def test_sigmoid_calibration_never_reverses_base_model_ranking() -> None:
    probability = np.array([0.05, 0.20, 0.80, 0.95])
    # Deliberately anti-correlated labels make unconstrained Platt fitting
    # prefer a negative coefficient.
    target = np.array([1, 1, 0, 0])
    fitted = fit_sigmoid_calibration(probability, target, np.ones(4))
    calibrated = fitted.predict(probability)

    assert fitted.coefficient > 0
    assert np.all(np.diff(calibrated) > 0)


def test_threshold_and_metrics_are_deterministic() -> None:
    target = np.array([0, 0, 1, 1])
    probability = np.array([0.1, 0.4, 0.6, 0.9])
    weights = np.ones(4)
    threshold, score = select_f1_threshold(
        target, probability, weights, grid_size=11
    )
    metrics = classification_metrics(
        target,
        probability,
        weights,
        threshold=threshold,
        top_fraction=0.5,
    )

    assert threshold == pytest.approx(0.6)
    assert score == pytest.approx(1.0)
    assert metrics["average_precision"] == pytest.approx(1.0)
    assert metrics["precision_at_fraction"] == pytest.approx(1.0)


def test_regression_metrics_include_rank_quality() -> None:
    metrics = regression_metrics(
        np.array([0.1, 0.2, 0.3]),
        np.array([0.15, 0.25, 0.35]),
        np.ones(3),
    )

    assert metrics["mae"] == pytest.approx(0.05)
    assert metrics["spearman"] == pytest.approx(1.0)


def test_subset_by_keys_preserves_key_order_and_rejects_missing(tmp_path: Path) -> None:
    dataset = pd.DataFrame(
        {
            "symbol": ["AAA", "BBB"],
            "date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "feature": [1.0, 2.0],
        }
    ).set_index(["symbol", "date"])
    keys = pd.DataFrame(
        {
            "symbol": ["BBB", "AAA"],
            "date": pd.to_datetime(["2024-01-03", "2024-01-02"]),
        }
    )
    key_path = tmp_path / "keys.parquet"
    keys.to_parquet(key_path, index=False)

    subset = subset_by_keys(dataset, key_path)
    assert subset["symbol"].tolist() == ["BBB", "AAA"]

    keys.loc[0, "symbol"] = "MISSING"
    keys.to_parquet(key_path, index=False)
    with pytest.raises(RuntimeError, match="missing from dataset"):
        subset_by_keys(dataset, key_path)


def test_config_and_best_round_policy(tmp_path: Path) -> None:
    payload = {
        "model_version": "test",
        "random_seed": 238,
        "n_jobs": 1,
        "classifier": {"n_estimators": 10},
        "strength_regressor": {"n_estimators": 9},
        "calibration": {"method": "sigmoid", "clip_epsilon": 1e-6},
        "decision": {
            "threshold_metric": "f1",
            "threshold_grid_size": 101,
            "precision_at_fraction": 0.05,
        },
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(json.dumps(payload), encoding="utf-8")

    config = XGBoostTrainingConfig.from_yaml(config_path)
    assert config.model_version == "test"
    assert median_best_round([10, 20, 30], 100) == 20
    assert median_best_round([], 100) == 100


def test_xgboost_classifier_and_strength_smoke_fit() -> None:
    random = np.random.default_rng(238)

    def make_frame(rows: int, start: str) -> pd.DataFrame:
        first_feature = random.normal(size=rows)
        target = (first_feature + random.normal(scale=0.4, size=rows) > 0).astype(int)
        strength = np.where(target == 1, 1 / (1 + np.exp(-first_feature)), np.nan)
        return pd.DataFrame(
            {
                "symbol": [f"S{index % 5}" for index in range(rows)],
                "date": pd.bdate_range(start, periods=rows),
                "feature_1": first_feature,
                "feature_2": random.normal(size=rows),
                "y_entry": target,
                "y_strength": strength,
                "sample_weight": np.ones(rows),
            }
        )

    train = make_frame(80, "2022-01-03")
    validation = make_frame(30, "2023-01-03")
    config = XGBoostTrainingConfig(
        model_version="smoke",
        random_seed=238,
        n_jobs=1,
        classifier={
            "objective": "binary:logistic",
            "eval_metric": "aucpr",
            "tree_method": "hist",
            "n_estimators": 12,
            "max_depth": 2,
            "learning_rate": 0.2,
            "early_stopping_rounds": 3,
        },
        strength_regressor={
            "objective": "reg:pseudohubererror",
            "eval_metric": "mae",
            "tree_method": "hist",
            "n_estimators": 12,
            "max_depth": 2,
            "learning_rate": 0.2,
            "early_stopping_rounds": 3,
        },
        calibration_method="sigmoid",
        calibration_clip_epsilon=1e-6,
        threshold_metric="f1",
        threshold_grid_size=101,
        precision_at_fraction=0.1,
    )

    predictions, metrics, classifier_rounds, strength_rounds = train_fold(
        "fold_smoke",
        train,
        validation,
        ["feature_1", "feature_2"],
        config,
    )

    assert predictions["p_entry_raw"].between(0, 1).all()
    assert predictions["p_strength"].between(0, 1).all()
    assert metrics["classification_average_precision"] > 0
    assert 1 <= classifier_rounds <= 12
    assert 1 <= strength_rounds <= 12


def test_temporal_calibration_uses_only_prior_folds() -> None:
    rows = []
    for fold_position, fold_id in enumerate(("fold_2020", "fold_2021", "fold_2022")):
        for index in range(20):
            target = index % 4 == 0
            rows.append(
                {
                    "fold_id": fold_id,
                    "y_entry": int(target),
                    "sample_weight": 1.0,
                    "p_entry_raw": 0.7 if target else 0.2 + fold_position * 0.02,
                }
            )
    oof, audit = temporal_calibration_predictions(
        pd.DataFrame(rows),
        clip_epsilon=1e-6,
        random_seed=238,
        threshold_grid_size=21,
        top_fraction=0.1,
    )

    first_fold = oof["fold_id"].eq("fold_2020")
    assert oof.loc[first_fold, "p_entry_calibrated_temporal"].isna().all()
    assert oof.loc[~first_fold, "p_entry_calibrated_temporal"].between(0, 1).all()
    assert audit.loc[audit["fold_id"].eq("fold_2021"), "calibration_folds"].item() == (
        "fold_2020"
    )
    assert audit.loc[audit["fold_id"].eq("fold_2022"), "calibration_folds"].item() == (
        "fold_2020,fold_2021"
    )
