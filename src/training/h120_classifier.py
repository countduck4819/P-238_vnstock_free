"""Controlled H120 classifier utilities for weight and feature ablations."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from src.training.xgboost_pipeline import XGBoostTrainingConfig, weighted_class_ratio

WEIGHT_POLICIES = {"baseline", "uniqueness"}


def attach_v3_label_weights(
    dataset: pd.DataFrame,
    labels: pd.DataFrame,
    *,
    policy: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Replace only the base sample weight after validating canonical labels."""
    if policy not in WEIGHT_POLICIES:
        raise ValueError(f"Unknown weight policy {policy!r}; expected {sorted(WEIGHT_POLICIES)}")
    keys = ["symbol", "date"]
    required_dataset = {*keys, "y_entry", "sample_weight"}
    required_labels = {*keys, "y_entry", "event_uniqueness_weight"}
    missing_dataset = sorted(required_dataset.difference(dataset.columns))
    missing_labels = sorted(required_labels.difference(labels.columns))
    if missing_dataset or missing_labels:
        raise ValueError(
            f"Missing dataset columns={missing_dataset}; label columns={missing_labels}"
        )
    if dataset.duplicated(keys).any() or labels.duplicated(keys).any():
        raise ValueError("Dataset and labels must be unique by symbol/date.")
    source = labels.loc[:, [*keys, "y_entry", "event_uniqueness_weight"]].rename(
        columns={"y_entry": "y_entry_v3"}
    )
    result = dataset.merge(source, on=keys, how="left", validate="one_to_one")
    if result["y_entry_v3"].isna().any():
        raise RuntimeError("V3 labels do not cover every H120 training row.")
    if not result["y_entry"].astype(int).eq(result["y_entry_v3"].astype(int)).all():
        raise RuntimeError("V3 labels change y_entry; this is not a weight-only ablation.")
    if policy == "baseline":
        result["sample_weight"] = 1.0
    else:
        result["sample_weight"] = result["event_uniqueness_weight"].astype(float)
    if not np.isfinite(result["sample_weight"]).all() or (result["sample_weight"] <= 0).any():
        raise RuntimeError("Ablation sample weights must be finite and positive.")
    audit = {
        "policy": policy,
        "rows": int(len(result)),
        "mean_weight": float(result["sample_weight"].mean()),
        "effective_sample_size": float(
            result["sample_weight"].sum() ** 2 / (result["sample_weight"] ** 2).sum()
        ),
        "min_weight": float(result["sample_weight"].min()),
        "max_weight": float(result["sample_weight"].max()),
    }
    return result.drop(columns=["y_entry_v3"]), audit


def fit_h120_classifier_fold(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    feature_columns: list[str],
    config: XGBoostTrainingConfig,
):
    """Fit a weighted binary H120 classifier and emit raw validation scores."""
    from xgboost import XGBClassifier

    required = {"symbol", "date", "y_entry", "sample_weight", *feature_columns}
    missing = sorted(required.difference(train.columns).union(required.difference(validation.columns)))
    if missing:
        raise ValueError(f"Classifier fold is missing columns: {missing}")
    x_train = train.loc[:, feature_columns]
    x_validation = validation.loc[:, feature_columns]
    # The frozen baseline uses XGBoost's native missing-value routing.  Some
    # otherwise feature-ready rows legitimately retain a short-window feature
    # gap, so an implicit imputation or row drop would change the experiment.
    if (
        np.isinf(x_train.to_numpy(dtype=float, na_value=np.nan)).any()
        or np.isinf(x_validation.to_numpy(dtype=float, na_value=np.nan)).any()
    ):
        raise ValueError("Classifier inputs contain infinite values.")
    y_train = train["y_entry"].astype(int)
    y_validation = validation["y_entry"].astype(int)
    train_weight = train["sample_weight"].astype(float)
    validation_weight = validation["sample_weight"].astype(float)
    parameters = dict(config.classifier)
    early_stopping_rounds = int(parameters.pop("early_stopping_rounds", 100))
    parameters.update(
        random_state=config.random_seed,
        n_jobs=config.n_jobs,
        verbosity=0,
        scale_pos_weight=weighted_class_ratio(y_train, train_weight),
    )
    model = XGBClassifier(**parameters, early_stopping_rounds=early_stopping_rounds)
    model.fit(
        x_train,
        y_train,
        sample_weight=train_weight,
        eval_set=[(x_validation, y_validation)],
        sample_weight_eval_set=[validation_weight],
        verbose=False,
    )
    prediction = validation.loc[:, ["symbol", "date", "y_entry", "sample_weight"]].copy()
    prediction["p_entry_raw"] = model.predict_proba(x_validation)[:, 1]
    best_iteration = getattr(model, "best_iteration", None)
    return model, prediction, {
        "weighted_class_ratio": weighted_class_ratio(y_train, train_weight),
        "best_iteration": int(best_iteration) + 1
        if best_iteration is not None
        else int(parameters["n_estimators"]),
    }
