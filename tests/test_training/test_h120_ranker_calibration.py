from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.training.h120_ranker_calibration import (
    assert_calibration_preserves_daily_ranking,
    causal_ranker_calibration_predictions,
)


def make_oof() -> pd.DataFrame:
    records: list[dict[str, object]] = []
    probabilities = [0.1, 0.3, 0.7, 0.9]
    labels = [0, 0, 1, 1]
    for fold_index, fold_id in enumerate(("fold_2020", "fold_2021", "fold_2022")):
        for day_offset in range(2):
            date = pd.Timestamp("2020-01-02") + pd.Timedelta(days=fold_index * 10 + day_offset)
            for symbol, probability, label in zip(("AAA", "BBB", "CCC", "DDD"), probabilities, labels):
                records.append(
                    {
                        "date": date,
                        "symbol": symbol,
                        "fold_id": fold_id,
                        "rank_score": np.log(probability / (1.0 - probability)),
                        "p_rank_raw": probability,
                        "y_entry": label,
                        "sample_weight": 1.0,
                        "market_regime_score": float(fold_index - 1),
                    }
                )
    return pd.DataFrame(records)


def test_static_and_rolling_calibration_use_only_prior_folds() -> None:
    oof = make_oof()
    static, static_audit = causal_ranker_calibration_predictions(
        oof,
        method="static_platt",
        output_column="p_static",
    )
    rolling, rolling_audit = causal_ranker_calibration_predictions(
        oof,
        method="rolling_platt",
        output_column="p_rolling",
        rolling_prior_folds=1,
    )

    assert static.loc[static["fold_id"].eq("fold_2020"), "p_static"].isna().all()
    assert rolling.loc[rolling["fold_id"].eq("fold_2020"), "p_rolling"].isna().all()
    assert static.loc[static["fold_id"].ne("fold_2020"), "p_static"].between(0, 1).all()
    assert static_audit.loc[static_audit["fold_id"].eq("fold_2021"), "calibration_folds"].item() == "fold_2020"
    assert rolling_audit.loc[rolling_audit["fold_id"].eq("fold_2022"), "calibration_folds"].item() == "fold_2021"


def test_regime_intercept_calibration_preserves_ranker_shortlist() -> None:
    calibrated, audit = causal_ranker_calibration_predictions(
        make_oof(),
        method="regime_intercept",
        output_column="p_regime",
        regime_column="market_regime_score",
    )

    assert audit.loc[audit["status"].eq("ok"), "ece"].notna().all()
    assert calibrated.loc[calibrated["fold_id"].ne("fold_2020"), "p_regime"].between(0, 1).all()
    assert_calibration_preserves_daily_ranking(
        calibrated,
        rank_column="rank_score",
        probability_column="p_regime",
        regime_column="market_regime_score",
    )


def test_regime_intercept_rejects_row_specific_regimes() -> None:
    frame = make_oof()
    frame.loc[frame["date"].eq(frame["date"].iloc[-1]), "market_regime_score"] = [0.0, 1.0, 0.0, 1.0]

    with pytest.raises(ValueError, match="date-common"):
        causal_ranker_calibration_predictions(
            frame,
            method="regime_intercept",
            output_column="p_regime",
            regime_column="market_regime_score",
        )
