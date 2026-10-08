from __future__ import annotations

import numpy as np
import pandas as pd

from src.training.h120_ranker import (
    H120RankerConfig,
    fit_h120_ranker_fold,
    prepare_ranking_frame,
    rank_score_to_probability,
    ranking_group_sizes,
)


def make_rows(start: str, days: int) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for day in pd.bdate_range(start, periods=days):
        for index, symbol in enumerate(("DDD", "AAA", "CCC", "BBB")):
            records.append(
                {
                    "date": day,
                    "symbol": symbol,
                    "feature_signal": float(3 - index),
                    "feature_noise": float(index % 2),
                    "y_entry": int(index == 0),
                }
            )
    return pd.DataFrame(records)


def test_ranker_orders_date_groups_and_keeps_probability_separate() -> None:
    train = make_rows("2020-01-01", 8)
    validation = make_rows("2020-02-01", 3)
    prepared = prepare_ranking_frame(train.sample(frac=1.0, random_state=238), ["feature_signal", "feature_noise"])
    assert prepared.groupby("date", sort=False)["symbol"].first().eq("AAA").all()
    assert ranking_group_sizes(prepared) == [4] * 8
    config = H120RankerConfig(
        model_version="test_ranker",
        random_seed=238,
        n_jobs=1,
        ranker={
            "objective": "rank:pairwise",
            "eval_metric": ["map@10", "ndcg@10"],
            "tree_method": "hist",
            "n_estimators": 12,
            "learning_rate": 0.2,
            "max_depth": 2,
            "min_child_weight": 1.0,
            "subsample": 1.0,
            "colsample_bytree": 1.0,
            "reg_lambda": 1.0,
            "early_stopping_rounds": 3,
        },
    )
    _, prediction = fit_h120_ranker_fold(
        train, validation, ["feature_signal", "feature_noise"], config
    )
    assert prediction["rank_score"].notna().all()
    assert prediction["p_rank_raw"].between(0, 1).all()
    assert np.all(np.diff(rank_score_to_probability(np.array([-2.0, 0.0, 2.0]))) > 0)
