import pandas as pd
import pytest

from src.labels import (
    ContinuationLabelConfig,
    attach_continuation_weight_components,
    continuation_event_id,
    label_continuation_symbol,
)


def make_config() -> ContinuationLabelConfig:
    return ContinuationLabelConfig(
        label_version="test",
        horizon=3,
        entry_lag=1,
        volatility_lookback=2,
        annualization_factor=252,
        excess_volatility_multiplier=0.0,
        minimum_excess_return=0.01,
        minimum_terminal_return=0.0,
        maximum_drawdown=-0.20,
        minimum_future_coverage=1.0,
        minimum_volatility_observations=2,
    )


def test_continuation_does_not_require_a_surge_onset() -> None:
    dates = pd.date_range("2020-01-01", periods=8, freq="D")
    stock = pd.DataFrame(
        {
            "date": dates,
            "open": [100, 100, 101, 102, 103, 104, 105, 106],
            "high": [101] * 8,
            "low": [99] * 8,
            "close": [100, 101, 102, 103, 104, 105, 106, 107],
            "volume": [1000] * 8,
        }
    )
    market = stock.copy()
    market["close"] = 100.0
    market["open"] = 100.0
    labels = label_continuation_symbol(
        "AAA", stock, market, pd.Series(True, index=dates), make_config()
    )
    assert labels["y_entry"].eq(1).any()
    assert labels.loc[labels["y_entry"].eq(1), "y_strength"].notna().all()
    labeled = labels["y_entry"].notna()
    assert labels.loc[labeled, "event_id"].notna().all()
    assert labels.loc[labeled, "event_id"].is_unique
    assert labels.loc[labeled, "event_start_date"].eq(labels.loc[labeled, "entry_date"]).all()
    first = labels.loc[labeled].iloc[0]
    assert first["event_id"] == continuation_event_id(
        first["label_version"], first["symbol"], first["entry_date"], first["label_end_date"]
    )
    assert first["event_id"].startswith("sha256:")
    assert first["event_id"] != continuation_event_id(
        first["label_version"],
        first["symbol"],
        first["entry_date"],
        first["label_end_date"] + pd.Timedelta(days=1),
    )


def test_continuation_censors_rows_without_future_horizon() -> None:
    dates = pd.date_range("2020-01-01", periods=4, freq="D")
    stock = pd.DataFrame(
        {
            "date": dates,
            "open": [100] * 4,
            "high": [100] * 4,
            "low": [100] * 4,
            "close": [100] * 4,
            "volume": [1000] * 4,
        }
    )
    labels = label_continuation_symbol(
        "AAA", stock, stock, pd.Series(True, index=dates), make_config()
    )
    assert labels.loc[labels["date"] > dates[-4], "y_entry"].isna().all()


def test_continuation_weight_components_are_normalized_and_fold_local() -> None:
    dates = pd.date_range("2020-01-01", periods=6, freq="D")
    rows = pd.DataFrame(
        {
            "symbol": ["AAA", "AAA", "BBB", "AAA", "AAA", "AAA"],
            "date": [dates[0], dates[1], dates[1], dates[2], dates[3], dates[4]],
            "entry_date": [dates[1], dates[2], dates[2], pd.NaT, pd.NaT, pd.NaT],
            "label_end_date": [dates[3], dates[4], dates[4], pd.NaT, pd.NaT, pd.NaT],
            "y_entry": [1, 0, 1, pd.NA, pd.NA, pd.NA],
        }
    )
    weighted = attach_continuation_weight_components(
        rows, class_balance_mode="full_ratio"
    )
    labeled = weighted["y_entry"].notna()
    assert weighted.loc[labeled, "event_uniqueness_weight"].notna().all()
    assert weighted.loc[labeled & weighted["symbol"].eq("AAA"), "event_uniqueness_weight"].lt(1).all()
    assert weighted.loc[weighted["y_entry"].eq(1), "class_balance_weight"].eq(0.5).all()
    assert weighted.loc[weighted["y_entry"].eq(0), "class_balance_weight"].eq(1.0).all()
    assert weighted.loc[labeled, "sample_weight_final"].mean() == pytest.approx(1.0)
