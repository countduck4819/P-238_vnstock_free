from __future__ import annotations

import pandas as pd
import pytest

from src.evaluation.h120_ranker_reporting import (
    summarize_daily_ranking_metrics,
    summarize_seed_metric_reports,
)


def make_daily() -> tuple[pd.DataFrame, pd.DataFrame]:
    daily = pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-01-02", "2020-01-03", "2021-01-04", "2021-01-05"]),
            "precision_at_k": [0.2, 0.4, 0.6, 0.8],
            "map_at_k": [0.1, 0.2, 0.3, 0.4],
            "ndcg_at_k": [0.2, 0.3, 0.4, 0.5],
            "lift": [1.0, 2.0, 3.0, 4.0],
        }
    )
    predictions = daily.loc[:, ["date"]].copy()
    predictions["symbol"] = "AAA"
    predictions["fold_id"] = ["fold_2020", "fold_2020", "fold_2021", "fold_2021"]
    return daily, predictions


def test_daily_ranking_summary_reports_mean_and_worst_fold() -> None:
    daily, predictions = make_daily()
    summary = summarize_daily_ranking_metrics(daily, predictions)

    assert summary["folds"] == ["fold_2020", "fold_2021"]
    assert summary["precision_at_k"]["mean"] == pytest.approx(0.5)
    assert summary["precision_at_k"]["worst_fold"] == pytest.approx(0.3)
    assert summary["lift"]["fold_means"]["fold_2021"] == pytest.approx(3.5)


def test_seed_summary_keeps_seed_variance_separate_from_dates() -> None:
    daily, predictions = make_daily()
    first = summarize_daily_ranking_metrics(daily, predictions)
    second = summarize_daily_ranking_metrics(daily.assign(precision_at_k=[0.3, 0.5, 0.7, 0.9]), predictions)

    summary = summarize_seed_metric_reports({238: first, 239: second})

    assert summary["precision_at_k"]["seed_mean"] == pytest.approx(0.55)
    assert summary["precision_at_k"]["seed_std"] == pytest.approx(0.05)
    assert summary["precision_at_k"]["worst_fold_over_seeds"] == pytest.approx(0.3)
