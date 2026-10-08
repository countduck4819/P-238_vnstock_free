from __future__ import annotations

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from src.features.wave_ignition import (
    FeatureConfig,
    build_feature_tables,
    compute_stock_features,
)


def make_ohlcv(periods: int = 180) -> pd.DataFrame:
    index = pd.bdate_range("2024-01-01", periods=periods, name="date")
    close = pd.Series(np.linspace(100, 150, periods), index=index)
    return pd.DataFrame(
        {
            "open": close - 0.2,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": np.linspace(1_000_000, 2_000_000, periods),
        },
        index=index,
    )


def test_breakout_uses_only_prior_prices() -> None:
    source = make_ohlcv()
    source.iloc[-1, source.columns.get_loc("close")] = 300
    source.iloc[-1, source.columns.get_loc("high")] = 301
    features = compute_stock_features(source, None, FeatureConfig())

    expected_previous_peak = source["close"].iloc[-61:-1].max()
    expected = source["close"].iloc[-1] / expected_previous_peak - 1
    assert np.isclose(features["breakout_distance_60"].iloc[-1], expected)
    assert features["is_breakout_60"].iloc[-1] == 1


def test_missing_session_is_not_forward_filled() -> None:
    source = make_ohlcv()
    missing_date = source.index[80]
    next_date = source.index[81]
    source.loc[missing_date] = np.nan
    features = compute_stock_features(source, None, FeatureConfig())

    assert missing_date not in features.index
    assert pd.isna(features.loc[next_date, "return_1d"])
    assert features.loc[next_date, "stale_sessions"] == 1


def test_features_are_prefix_invariant() -> None:
    source = make_ohlcv(320)
    truncated = source.iloc[:250]
    full_features = compute_stock_features(source, None, FeatureConfig()).iloc[:250]
    truncated_features = compute_stock_features(truncated, None, FeatureConfig())

    assert_frame_equal(
        full_features,
        truncated_features,
        check_dtype=False,
        check_exact=False,
        rtol=1e-12,
        atol=1e-12,
    )


def test_quality_inputs_respect_expected_ranges() -> None:
    features = compute_stock_features(make_ohlcv(), None, FeatureConfig())

    assert features["coverage_20"].between(0, 1).all()
    assert features["zero_volume_ratio_20"].dropna().between(0, 1).all()
    assert (features["natr_20"].dropna() >= 0).all()


def test_end_to_end_feature_tables_have_unique_causal_keys() -> None:
    base = make_ohlcv(320).reset_index()
    symbols = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
    stocks = []
    for offset, symbol in enumerate(symbols):
        frame = base.copy()
        scale = 1.0 + offset / 100
        frame[["open", "high", "low", "close"]] *= scale
        frame["symbol"] = symbol
        stocks.append(frame)
    stock = pd.concat(stocks, ignore_index=True)
    vnindex = base.copy()
    industry = pd.DataFrame(
        {
            "symbol": symbols,
            "icb_level_2_code": ["1000"] * len(symbols),
            "icb_level_2_name": ["Synthetic"] * len(symbols),
        }
    )

    stock_features, market_features, sector_features = build_feature_tables(
        stock,
        vnindex,
        industry,
        FeatureConfig(zscore_min_periods=20, zscore_window=60),
    )

    assert not stock_features.duplicated(["symbol", "date"]).any()
    assert len(market_features) == len(vnindex)
    assert sector_features["icb_level_2_code"].nunique() == 1
    assert stock_features["feature_version"].eq("wave_ignition_v1").all()
    assert stock_features["market_regime_score"].notna().any()
