from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.models.wave_xgboost import WaveXGBoostPredictor
from src.training.xgboost_pipeline import SigmoidCalibration


class FakeClassifier:
    def predict_proba(self, matrix: pd.DataFrame) -> np.ndarray:
        positive = np.asarray(matrix["feature_1"], dtype=float)
        return np.column_stack([1.0 - positive, positive])


class FakeRegressor:
    def predict(self, matrix: pd.DataFrame) -> np.ndarray:
        return np.asarray(matrix["feature_2"], dtype=float)


def make_predictor() -> WaveXGBoostPredictor:
    return WaveXGBoostPredictor(
        classifier=FakeClassifier(),  # type: ignore[arg-type]
        strength_regressor=FakeRegressor(),  # type: ignore[arg-type]
        calibrator=SigmoidCalibration(coefficient=1.0, intercept=0.0),
        feature_columns=["feature_1", "feature_2"],
        decision_threshold=0.5,
        model_manifest={"model_version": "test"},
    )


def test_predictor_returns_entry_strength_and_composite_score() -> None:
    frame = pd.DataFrame(
        {
            "symbol": ["AAA", "BBB"],
            "date": pd.to_datetime(["2025-01-02", "2025-01-03"]),
            "feature_1": [0.2, 0.8],
            "feature_2": [0.4, 0.7],
        }
    )

    predictions = make_predictor().predict(frame)

    assert predictions["predicted_entry"].tolist() == [0, 1]
    assert predictions["p_strength_conditional"].tolist() == pytest.approx([0.4, 0.7])
    assert predictions["wave_score"].tolist() == pytest.approx([0.08, 0.56])


def test_predictor_rejects_missing_or_infinite_features() -> None:
    predictor = make_predictor()
    with pytest.raises(ValueError, match="Missing model features"):
        predictor.predict(pd.DataFrame({"feature_1": [0.5]}))
    with pytest.raises(ValueError, match="infinite"):
        predictor.predict(
            pd.DataFrame({"feature_1": [0.5], "feature_2": [np.inf]})
        )
