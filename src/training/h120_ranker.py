"""Stock-only XGBoost ranking utilities for the H120 research challenger."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml


@dataclass(frozen=True)
class H120RankerConfig:
    """Versioned ranker policy; probability calibration is deliberately separate."""

    model_version: str
    random_seed: int
    n_jobs: int
    ranker: dict[str, Any]

    @classmethod
    def from_yaml(cls, path: Path) -> H120RankerConfig:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        ranker = dict(payload["ranker"])
        if ranker.get("objective") != "rank:pairwise":
            raise ValueError("The first H120 ranker must use objective=rank:pairwise.")
        metrics = ranker.get("eval_metric", [])
        metrics = [metrics] if isinstance(metrics, str) else list(metrics)
        if "map@10" not in metrics or "ndcg@10" not in metrics:
            raise ValueError("Ranker evaluation must report map@10 and ndcg@10.")
        return cls(
            model_version=str(payload["model_version"]),
            random_seed=int(payload["random_seed"]),
            n_jobs=int(payload["n_jobs"]),
            ranker=ranker,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_version": self.model_version,
            "random_seed": self.random_seed,
            "n_jobs": self.n_jobs,
            "ranker": self.ranker,
        }


def prepare_ranking_frame(frame: pd.DataFrame, feature_columns: list[str]) -> pd.DataFrame:
    """Validate and deterministically order rows into date query groups."""
    required = {"symbol", "date", "y_entry", *feature_columns}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Ranking frame is missing: {missing}")
    result = frame.loc[frame["y_entry"].notna()].copy()
    result["date"] = pd.to_datetime(result["date"], errors="raise")
    result.sort_values(["date", "symbol"], inplace=True, kind="stable")
    result.reset_index(drop=True, inplace=True)
    if result.duplicated(["date", "symbol"]).any():
        raise ValueError("Ranking frame has duplicate date/symbol rows.")
    if result.empty or result["y_entry"].nunique() < 2:
        raise ValueError("Ranking frame requires both target classes.")
    return result


def ranking_group_sizes(frame: pd.DataFrame) -> list[int]:
    """Return XGBoost query sizes after ``prepare_ranking_frame`` ordering."""
    if not frame["date"].is_monotonic_increasing:
        raise ValueError("Ranking groups require a date-sorted frame.")
    return frame.groupby("date", observed=True, sort=False).size().astype(int).tolist()


def rank_score_to_probability(score: np.ndarray | pd.Series) -> np.ndarray:
    """Monotonic pre-calibration map from raw rank score to (0, 1)."""
    values = np.asarray(score, dtype=float)
    return 1.0 / (1.0 + np.exp(-np.clip(values, -30.0, 30.0)))


def fit_h120_ranker_fold(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    feature_columns: list[str],
    config: H120RankerConfig,
):
    """Fit one date-grouped ranker fold and return raw validation rank scores.

    Row-level class/sample weights are intentionally not passed to pairwise
    ranking. XGBoost interprets ranker weights at query-group level, so a row
    weight policy would be semantically incorrect without a dedicated ablation.
    """
    from xgboost import XGBRanker

    train_rows = prepare_ranking_frame(train, feature_columns)
    validation_rows = prepare_ranking_frame(validation, feature_columns)
    parameters = dict(config.ranker)
    early_stopping_rounds = int(parameters.pop("early_stopping_rounds", 100))
    model = XGBRanker(
        **parameters,
        random_state=config.random_seed,
        n_jobs=config.n_jobs,
        early_stopping_rounds=early_stopping_rounds,
    )
    model.fit(
        train_rows[feature_columns],
        train_rows["y_entry"].astype(float),
        group=ranking_group_sizes(train_rows),
        eval_set=[(validation_rows[feature_columns], validation_rows["y_entry"].astype(float))],
        eval_group=[ranking_group_sizes(validation_rows)],
        verbose=False,
    )
    prediction = validation_rows.loc[:, ["symbol", "date", "y_entry"]].copy()
    prediction["rank_score"] = model.predict(validation_rows[feature_columns])
    prediction["p_rank_raw"] = rank_score_to_probability(prediction["rank_score"])
    return model, prediction
