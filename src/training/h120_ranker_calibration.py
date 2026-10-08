"""Causal probability calibration for a ranker whose ordering stays immutable."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss

from src.training.xgboost_pipeline import SigmoidCalibration, fit_sigmoid_calibration


@dataclass(frozen=True)
class RankerProbabilityCalibrator:
    """Positive-slope Platt mapping with an optional date-common regime intercept."""

    coefficient: float
    intercept: float
    clip_epsilon: float
    regime_coefficient: float = 0.0

    def predict(
        self,
        probability: np.ndarray | pd.Series,
        regime: np.ndarray | pd.Series | None = None,
    ) -> np.ndarray:
        values = np.asarray(probability, dtype=float)
        clipped = np.clip(values, self.clip_epsilon, 1.0 - self.clip_epsilon)
        logits = np.log(clipped / (1.0 - clipped))
        regime_values = 0.0 if regime is None else np.asarray(regime, dtype=float)
        score = self.coefficient * logits + self.intercept + self.regime_coefficient * regime_values
        return 1.0 / (1.0 + np.exp(-np.clip(score, -30.0, 30.0)))


def _validate_binary_arrays(
    probability: np.ndarray | pd.Series,
    target: np.ndarray | pd.Series,
    sample_weight: np.ndarray | pd.Series,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    probabilities = np.asarray(probability, dtype=float)
    labels = np.asarray(target, dtype=int)
    weights = np.asarray(sample_weight, dtype=float)
    if probabilities.shape != labels.shape or labels.shape != weights.shape:
        raise ValueError("Calibration arrays must have the same shape.")
    if np.unique(labels).size != 2:
        raise ValueError("Calibration requires both binary classes.")
    return probabilities, labels, weights


def fit_regime_intercept_calibration(
    probability: np.ndarray | pd.Series,
    target: np.ndarray | pd.Series,
    sample_weight: np.ndarray | pd.Series,
    regime: np.ndarray | pd.Series,
    *,
    clip_epsilon: float = 1e-6,
    random_seed: int = 238,
) -> RankerProbabilityCalibrator:
    """Fit a positive score slope plus a market-regime intercept adjustment."""
    probabilities, labels, weights = _validate_binary_arrays(probability, target, sample_weight)
    regime_values = np.asarray(regime, dtype=float)
    if regime_values.shape != probabilities.shape or not np.isfinite(regime_values).all():
        raise ValueError("Regime calibration requires a finite regime value for every row.")
    clipped = np.clip(probabilities, clip_epsilon, 1.0 - clip_epsilon)
    logits = np.log(clipped / (1.0 - clipped))
    model = LogisticRegression(C=1e6, solver="lbfgs", random_state=random_seed)
    model.fit(np.column_stack([logits, regime_values]), labels, sample_weight=weights)
    coefficient = float(model.coef_[0, 0])
    if coefficient <= 0.0:
        fallback = fit_sigmoid_calibration(
            probabilities,
            labels,
            weights,
            clip_epsilon=clip_epsilon,
            random_seed=random_seed,
        )
        return RankerProbabilityCalibrator(
            coefficient=fallback.coefficient,
            intercept=fallback.intercept,
            clip_epsilon=clip_epsilon,
        )
    return RankerProbabilityCalibrator(
        coefficient=coefficient,
        intercept=float(model.intercept_[0]),
        regime_coefficient=float(model.coef_[0, 1]),
        clip_epsilon=clip_epsilon,
    )


def expected_calibration_error(
    target: np.ndarray | pd.Series,
    probability: np.ndarray | pd.Series,
    sample_weight: np.ndarray | pd.Series,
    *,
    bins: int = 10,
) -> float:
    """Weighted equal-width ECE with bins fixed before inspecting outcomes."""
    labels = np.asarray(target, dtype=float)
    probabilities = np.asarray(probability, dtype=float)
    weights = np.asarray(sample_weight, dtype=float)
    if bins < 2:
        raise ValueError("ECE requires at least two bins.")
    edges = np.linspace(0.0, 1.0, bins + 1)
    bucket = np.minimum(np.digitize(probabilities, edges, right=True), bins) - 1
    total_weight = float(weights.sum())
    if total_weight <= 0:
        return float("nan")
    ece = 0.0
    for index in range(bins):
        selected = bucket == index
        if not selected.any():
            continue
        weight = weights[selected]
        fraction = float(weight.sum() / total_weight)
        observed = float(np.average(labels[selected], weights=weight))
        predicted = float(np.average(probabilities[selected], weights=weight))
        ece += fraction * abs(observed - predicted)
    return float(ece)


def probability_diagnostics(
    target: np.ndarray | pd.Series,
    probability: np.ndarray | pd.Series,
    sample_weight: np.ndarray | pd.Series,
    *,
    clip_epsilon: float,
    random_seed: int,
    ece_bins: int,
) -> dict[str, float]:
    """Return calibration diagnostics without ever treating them as ranking metrics."""
    probabilities, labels, weights = _validate_binary_arrays(probability, target, sample_weight)
    clipped = np.clip(probabilities, clip_epsilon, 1.0 - clip_epsilon)
    logits = np.log(clipped / (1.0 - clipped)).reshape(-1, 1)
    calibration_model = LogisticRegression(C=1e6, solver="lbfgs", random_state=random_seed)
    calibration_model.fit(logits, labels, sample_weight=weights)
    return {
        "brier_score": float(brier_score_loss(labels, probabilities, sample_weight=weights)),
        "log_loss": float(log_loss(labels, probabilities, sample_weight=weights)),
        "ece": expected_calibration_error(labels, probabilities, weights, bins=ece_bins),
        "calibration_slope": float(calibration_model.coef_[0, 0]),
        "calibration_intercept": float(calibration_model.intercept_[0]),
        "predicted_prevalence": float(np.average(probabilities, weights=weights)),
        "observed_prevalence": float(np.average(labels, weights=weights)),
    }


def assert_calibration_preserves_daily_ranking(
    frame: pd.DataFrame,
    *,
    rank_column: str,
    probability_column: str,
    regime_column: str | None = None,
    k: int = 10,
) -> None:
    """Fail closed if a probability output could change the ranker shortlist."""
    if regime_column:
        per_date_regimes = frame.groupby("date", observed=True)[regime_column].nunique(dropna=False)
        if (per_date_regimes > 1).any():
            raise ValueError("Regime calibration requires a date-common regime value.")
    scored = frame.loc[frame[probability_column].notna()].copy()
    for _, group in scored.groupby("date", observed=True, sort=True):
        rank_order = group.sort_values([rank_column, "symbol"], ascending=[False, True], kind="stable")
        probability_order = group.sort_values(
            [probability_column, "symbol"], ascending=[False, True], kind="stable"
        )
        if not rank_order["symbol"].head(k).tolist() == probability_order["symbol"].head(k).tolist():
            raise ValueError("Calibration changed the ranker Top-K order.")


def causal_ranker_calibration_predictions(
    oof: pd.DataFrame,
    *,
    method: str,
    output_column: str,
    score_probability_column: str = "p_rank_raw",
    regime_column: str | None = None,
    rolling_prior_folds: int | None = None,
    clip_epsilon: float = 1e-6,
    random_seed: int = 238,
    ece_bins: int = 10,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Calibrate a ranker fold using only earlier OOF folds with mature labels."""
    if method not in {"static_platt", "rolling_platt", "regime_intercept"}:
        raise ValueError(f"Unsupported ranker calibration method: {method}")
    required = {"date", "fold_id", "symbol", "y_entry", "sample_weight", score_probability_column}
    if method == "regime_intercept":
        if not regime_column:
            raise ValueError("Regime-intercept calibration requires regime_column.")
        required.add(regime_column)
    missing = sorted(required.difference(oof.columns))
    if missing:
        raise ValueError(f"Ranker OOF is missing calibration columns: {missing}")
    result = oof.copy()
    result[output_column] = np.nan
    folds = sorted(str(fold) for fold in result["fold_id"].unique())
    audit: list[dict[str, Any]] = []
    for position, fold_id in enumerate(folds):
        if position == 0:
            audit.append({"fold_id": fold_id, "status": "insufficient_prior_oof", "calibration_folds": ""})
            continue
        prior_folds = folds[:position]
        if method == "rolling_platt":
            if not rolling_prior_folds or rolling_prior_folds < 1:
                raise ValueError("Rolling Platt requires rolling_prior_folds >= 1.")
            prior_folds = prior_folds[-rolling_prior_folds:]
        calibration_rows = result["fold_id"].isin(prior_folds)
        evaluation_rows = result["fold_id"].eq(fold_id)
        calibration = result.loc[calibration_rows]
        if method == "regime_intercept":
            calibrator = fit_regime_intercept_calibration(
                calibration[score_probability_column],
                calibration["y_entry"],
                calibration["sample_weight"],
                calibration[regime_column],
                clip_epsilon=clip_epsilon,
                random_seed=random_seed,
            )
            probabilities = calibrator.predict(
                result.loc[evaluation_rows, score_probability_column],
                result.loc[evaluation_rows, regime_column],
            )
        else:
            platt: SigmoidCalibration = fit_sigmoid_calibration(
                calibration[score_probability_column],
                calibration["y_entry"],
                calibration["sample_weight"],
                clip_epsilon=clip_epsilon,
                random_seed=random_seed,
            )
            calibrator = RankerProbabilityCalibrator(
                coefficient=platt.coefficient,
                intercept=platt.intercept,
                clip_epsilon=platt.clip_epsilon,
            )
            probabilities = calibrator.predict(result.loc[evaluation_rows, score_probability_column])
        result.loc[evaluation_rows, output_column] = probabilities
        diagnostics = probability_diagnostics(
            result.loc[evaluation_rows, "y_entry"],
            probabilities,
            result.loc[evaluation_rows, "sample_weight"],
            clip_epsilon=clip_epsilon,
            random_seed=random_seed,
            ece_bins=ece_bins,
        )
        audit.append(
            {
                "fold_id": fold_id,
                "status": "ok",
                "calibration_folds": ",".join(prior_folds),
                "calibration_coefficient": calibrator.coefficient,
                "calibration_intercept": calibrator.intercept,
                "regime_coefficient": calibrator.regime_coefficient,
                **diagnostics,
            }
        )
    assert_calibration_preserves_daily_ranking(
        result,
        rank_column="rank_score",
        probability_column=output_column,
        regime_column=regime_column if method == "regime_intercept" else None,
    )
    return result, pd.DataFrame(audit)
