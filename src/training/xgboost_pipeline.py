"""Utilities for leakage-aware XGBoost wave-model training."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    f1_score,
    log_loss,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    recall_score,
    roc_auc_score,
)


@dataclass(frozen=True)
class XGBoostTrainingConfig:
    """Versioned model and evaluation policy."""

    model_version: str
    random_seed: int
    n_jobs: int
    classifier: dict[str, Any]
    strength_regressor: dict[str, Any]
    calibration_method: str
    calibration_clip_epsilon: float
    threshold_metric: str
    threshold_grid_size: int
    precision_at_fraction: float

    @classmethod
    def from_yaml(cls, path: Path) -> XGBoostTrainingConfig:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        calibration = payload["calibration"]
        decision = payload["decision"]
        if calibration["method"] != "sigmoid":
            raise ValueError("Only leakage-controlled sigmoid calibration is supported.")
        if decision["threshold_metric"] != "f1":
            raise ValueError("Only the f1 threshold policy is currently supported.")
        fraction = float(decision["precision_at_fraction"])
        if not 0 < fraction <= 1:
            raise ValueError("precision_at_fraction must be in (0, 1].")
        return cls(
            model_version=str(payload["model_version"]),
            random_seed=int(payload["random_seed"]),
            n_jobs=int(payload["n_jobs"]),
            classifier=dict(payload["classifier"]),
            strength_regressor=dict(payload["strength_regressor"]),
            calibration_method=str(calibration["method"]),
            calibration_clip_epsilon=float(calibration["clip_epsilon"]),
            threshold_metric=str(decision["threshold_metric"]),
            threshold_grid_size=int(decision["threshold_grid_size"]),
            precision_at_fraction=fraction,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_version": self.model_version,
            "random_seed": self.random_seed,
            "n_jobs": self.n_jobs,
            "classifier": self.classifier,
            "strength_regressor": self.strength_regressor,
            "calibration": {
                "method": self.calibration_method,
                "clip_epsilon": self.calibration_clip_epsilon,
            },
            "decision": {
                "threshold_metric": self.threshold_metric,
                "threshold_grid_size": self.threshold_grid_size,
                "precision_at_fraction": self.precision_at_fraction,
            },
        }


@dataclass(frozen=True)
class SigmoidCalibration:
    """Serializable Platt-style mapping from raw probability to calibrated probability."""

    coefficient: float
    intercept: float
    clip_epsilon: float = 1e-6

    def predict(self, probability: np.ndarray | pd.Series) -> np.ndarray:
        values = np.asarray(probability, dtype=float)
        clipped = np.clip(values, self.clip_epsilon, 1.0 - self.clip_epsilon)
        logits = np.log(clipped / (1.0 - clipped))
        score = np.clip(self.coefficient * logits + self.intercept, -30.0, 30.0)
        return 1.0 / (1.0 + np.exp(-score))

    def to_dict(self) -> dict[str, float | str]:
        return {
            "method": "sigmoid",
            "coefficient": self.coefficient,
            "intercept": self.intercept,
            "clip_epsilon": self.clip_epsilon,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SigmoidCalibration:
        if payload.get("method") != "sigmoid":
            raise ValueError("Unsupported calibration method.")
        return cls(
            coefficient=float(payload["coefficient"]),
            intercept=float(payload["intercept"]),
            clip_epsilon=float(payload["clip_epsilon"]),
        )


def fit_sigmoid_calibration(
    probability: np.ndarray | pd.Series,
    target: np.ndarray | pd.Series,
    sample_weight: np.ndarray | pd.Series,
    *,
    clip_epsilon: float = 1e-6,
    random_seed: int = 238,
) -> SigmoidCalibration:
    """Fit calibration only from out-of-fold predictions."""
    probabilities = np.asarray(probability, dtype=float)
    labels = np.asarray(target, dtype=int)
    weights = np.asarray(sample_weight, dtype=float)
    if probabilities.shape != labels.shape or labels.shape != weights.shape:
        raise ValueError("Calibration arrays must have the same shape.")
    if np.unique(labels).size != 2:
        raise ValueError("Calibration requires both binary classes.")
    clipped = np.clip(probabilities, clip_epsilon, 1.0 - clip_epsilon)
    logits = np.log(clipped / (1.0 - clipped)).reshape(-1, 1)
    model = LogisticRegression(C=1e6, solver="lbfgs", random_state=random_seed)
    model.fit(logits, labels, sample_weight=weights)
    coefficient = float(model.coef_[0, 0])
    intercept = float(model.intercept_[0])
    if coefficient <= 0.0:
        # A calibrator must never reverse the ranking learned by the base
        # model. Regime shifts can make unconstrained Platt fitting choose a
        # negative slope (notably when one prior fold has an extreme event
        # prevalence). Fall back to a unit positive slope and solve only the
        # intercept so the weighted mean matches historical prevalence.
        prevalence = float(np.average(labels, weights=weights))
        target = np.clip(prevalence, clip_epsilon, 1.0 - clip_epsilon)
        lower, upper = -30.0, 30.0
        flat_logits = logits.ravel()
        for _ in range(80):
            midpoint = (lower + upper) / 2.0
            calibrated = 1.0 / (
                1.0 + np.exp(-np.clip(flat_logits + midpoint, -30.0, 30.0))
            )
            if float(np.average(calibrated, weights=weights)) < target:
                lower = midpoint
            else:
                upper = midpoint
        coefficient = 1.0
        intercept = (lower + upper) / 2.0
    return SigmoidCalibration(
        coefficient=coefficient,
        intercept=intercept,
        clip_epsilon=clip_epsilon,
    )


def weighted_class_ratio(
    target: np.ndarray | pd.Series,
    sample_weight: np.ndarray | pd.Series,
) -> float:
    """Return weighted negative/positive mass for XGBoost scale_pos_weight."""
    labels = np.asarray(target, dtype=int)
    weights = np.asarray(sample_weight, dtype=float)
    if labels.shape != weights.shape:
        raise ValueError("target and sample_weight must have the same shape.")
    if not np.isin(labels, [0, 1]).all():
        raise ValueError("target must contain only 0 and 1.")
    positive_mass = float(weights[labels == 1].sum())
    negative_mass = float(weights[labels == 0].sum())
    if positive_mass <= 0 or negative_mass <= 0:
        raise ValueError("Both classes must have positive sample-weight mass.")
    return negative_mass / positive_mass


def select_f1_threshold(
    target: np.ndarray | pd.Series,
    probability: np.ndarray | pd.Series,
    sample_weight: np.ndarray | pd.Series,
    *,
    grid_size: int = 401,
) -> tuple[float, float]:
    """Select a deterministic OOF threshold; prefer the larger threshold on ties."""
    labels = np.asarray(target, dtype=int)
    probabilities = np.asarray(probability, dtype=float)
    weights = np.asarray(sample_weight, dtype=float)
    if grid_size < 2:
        raise ValueError("grid_size must be at least 2.")
    unique_probabilities = np.unique(probabilities)
    if len(unique_probabilities) <= grid_size:
        thresholds = unique_probabilities
    else:
        positions = np.linspace(0, len(unique_probabilities) - 1, grid_size)
        thresholds = unique_probabilities[np.round(positions).astype(int)]
    scores = np.asarray(
        [
            f1_score(
                labels,
                probabilities >= threshold,
                sample_weight=weights,
                zero_division=0,
            )
            for threshold in thresholds
        ]
    )
    best_score = float(scores.max())
    best_threshold = float(thresholds[np.flatnonzero(scores == best_score)[-1]])
    return best_threshold, best_score


def classification_metrics(
    target: np.ndarray | pd.Series,
    probability: np.ndarray | pd.Series,
    sample_weight: np.ndarray | pd.Series,
    *,
    threshold: float,
    top_fraction: float,
) -> dict[str, float]:
    labels = np.asarray(target, dtype=int)
    probabilities = np.asarray(probability, dtype=float)
    weights = np.asarray(sample_weight, dtype=float)
    predicted = probabilities >= threshold
    top_count = max(1, int(np.ceil(len(labels) * top_fraction)))
    top_indices = np.argsort(-probabilities, kind="stable")[:top_count]
    top_labels = labels[top_indices]
    top_weights = weights[top_indices]
    result = {
        "rows": float(len(labels)),
        "row_positive_rate": float(labels.mean()),
        "positive_rate": float(np.average(labels, weights=weights)),
        "average_precision": float(
            average_precision_score(labels, probabilities, sample_weight=weights)
        ),
        "log_loss": float(log_loss(labels, probabilities, sample_weight=weights)),
        "brier_score": float(
            brier_score_loss(labels, probabilities, sample_weight=weights)
        ),
        "precision": float(
            precision_score(labels, predicted, sample_weight=weights, zero_division=0)
        ),
        "recall": float(
            recall_score(labels, predicted, sample_weight=weights, zero_division=0)
        ),
        "f1": float(
            f1_score(labels, predicted, sample_weight=weights, zero_division=0)
        ),
        "precision_at_fraction": float(top_labels.mean()),
        "weighted_precision_at_fraction": float(
            np.average(top_labels, weights=top_weights)
        ),
        "recall_at_fraction": float(top_labels.sum() / max(labels.sum(), 1)),
        "weighted_recall_at_fraction": float(
            weights[top_indices][top_labels == 1].sum()
            / max(weights[labels == 1].sum(), np.finfo(float).eps)
        ),
        "top_fraction": float(top_fraction),
        "threshold": float(threshold),
    }
    if np.unique(labels).size == 2:
        result["roc_auc"] = float(
            roc_auc_score(labels, probabilities, sample_weight=weights)
        )
    else:
        result["roc_auc"] = float("nan")
    return result


def regression_metrics(
    target: np.ndarray | pd.Series,
    prediction: np.ndarray | pd.Series,
    sample_weight: np.ndarray | pd.Series,
) -> dict[str, float]:
    labels = np.asarray(target, dtype=float)
    predictions = np.asarray(prediction, dtype=float)
    weights = np.asarray(sample_weight, dtype=float)
    label_rank = pd.Series(labels).rank(method="average").to_numpy()
    prediction_rank = pd.Series(predictions).rank(method="average").to_numpy()
    if np.std(label_rank) == 0 or np.std(prediction_rank) == 0:
        spearman = float("nan")
    else:
        spearman = float(np.corrcoef(label_rank, prediction_rank)[0, 1])
    return {
        "rows": float(len(labels)),
        "mae": float(mean_absolute_error(labels, predictions, sample_weight=weights)),
        "rmse": float(
            np.sqrt(mean_squared_error(labels, predictions, sample_weight=weights))
        ),
        "spearman": spearman,
    }


def temporal_calibration_predictions(
    oof: pd.DataFrame,
    *,
    clip_epsilon: float,
    random_seed: int,
    threshold_grid_size: int,
    top_fraction: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Calibrate each fold using strictly earlier OOF folds."""
    result = oof.copy()
    result["p_entry_calibrated_temporal"] = np.nan
    result["temporal_threshold"] = np.nan
    result["predicted_entry_temporal"] = pd.Series(
        pd.NA, index=result.index, dtype="Int8"
    )
    folds = sorted(result["fold_id"].unique())
    audit: list[dict[str, Any]] = []
    for fold_position, fold_id in enumerate(folds):
        if fold_position == 0:
            audit.append(
                {
                    "fold_id": fold_id,
                    "status": "insufficient_prior_oof",
                    "calibration_folds": "",
                }
            )
            continue
        prior_folds = folds[:fold_position]
        calibration_rows = result["fold_id"].isin(prior_folds)
        evaluation_rows = result["fold_id"].eq(fold_id)
        calibrator = fit_sigmoid_calibration(
            result.loc[calibration_rows, "p_entry_raw"],
            result.loc[calibration_rows, "y_entry"],
            result.loc[calibration_rows, "sample_weight"],
            clip_epsilon=clip_epsilon,
            random_seed=random_seed,
        )
        calibration_probability = calibrator.predict(
            result.loc[calibration_rows, "p_entry_raw"]
        )
        threshold, _ = select_f1_threshold(
            result.loc[calibration_rows, "y_entry"],
            calibration_probability,
            result.loc[calibration_rows, "sample_weight"],
            grid_size=threshold_grid_size,
        )
        evaluation_probability = calibrator.predict(
            result.loc[evaluation_rows, "p_entry_raw"]
        )
        result.loc[evaluation_rows, "p_entry_calibrated_temporal"] = (
            evaluation_probability
        )
        result.loc[evaluation_rows, "temporal_threshold"] = threshold
        result.loc[evaluation_rows, "predicted_entry_temporal"] = (
            evaluation_probability >= threshold
        ).astype("int8")
        metrics = classification_metrics(
            result.loc[evaluation_rows, "y_entry"],
            evaluation_probability,
            result.loc[evaluation_rows, "sample_weight"],
            threshold=threshold,
            top_fraction=top_fraction,
        )
        audit.append(
            {
                "fold_id": fold_id,
                "status": "ok",
                "calibration_folds": ",".join(prior_folds),
                "calibration_coefficient": calibrator.coefficient,
                "calibration_intercept": calibrator.intercept,
                **metrics,
            }
        )
    return result, pd.DataFrame(audit)


def median_best_round(best_rounds: list[int], configured_rounds: int) -> int:
    valid = [int(value) for value in best_rounds if int(value) > 0]
    if not valid:
        return int(configured_rounds)
    return max(1, int(np.median(valid)))


def subset_by_keys(
    indexed_dataset: pd.DataFrame,
    keys_path: Path,
) -> pd.DataFrame:
    """Load an exact split by key without allowing missing or duplicate rows."""
    keys = pd.read_parquet(keys_path)
    keys["date"] = pd.to_datetime(keys["date"], errors="raise")
    if keys.duplicated(["symbol", "date"]).any():
        raise RuntimeError(f"Duplicate keys in {keys_path}")
    lookup = pd.MultiIndex.from_frame(keys[["symbol", "date"]])
    positions = indexed_dataset.index.get_indexer(lookup)
    if (positions < 0).any():
        raise RuntimeError(f"Split keys missing from dataset: {(positions < 0).sum()}")
    result = indexed_dataset.iloc[positions].copy()
    result.reset_index(inplace=True)
    return result
