import numpy as np
import pandas as pd

from src.features.technical_experimental import EXPERIMENTAL_FEATURES, add_experimental_features


def test_experimental_features_are_causal_and_have_expected_columns():
    dates = pd.date_range("2020-01-01", periods=80, freq="D")
    close = pd.Series(np.linspace(100.0, 140.0, len(dates)), index=dates)
    frame = pd.DataFrame(
        {
            "close": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "volume": 1000.0,
            "distance_ma20": 0.01,
            "natr_20": 0.02,
            "volume_ratio_20": 1.0,
        },
        index=dates,
    )
    result = add_experimental_features(frame)
    assert set(EXPERIMENTAL_FEATURES).issubset(result.columns)
    assert pd.isna(result.loc[dates[0], "return_1d_simple"])
    assert pd.isna(result.loc[dates[0], "rsi_14"])
    altered = frame.copy()
    altered.loc[dates[60]:, "close"] *= 5.0
    altered_result = add_experimental_features(altered)
    pd.testing.assert_frame_equal(
        result.loc[: dates[59], list(EXPERIMENTAL_FEATURES)],
        altered_result.loc[: dates[59], list(EXPERIMENTAL_FEATURES)],
    )


def test_rsi_handles_monotonic_and_flat_prices():
    dates = pd.date_range("2020-01-01", periods=40, freq="D")

    def source(close):
        close = pd.Series(close, index=dates, dtype=float)
        return pd.DataFrame(
            {
                "close": close,
                "high": close + 1,
                "low": close - 1,
                "volume": 1000.0,
                "distance_ma20": 0.0,
                "natr_20": 0.02,
                "volume_ratio_20": 1.0,
            },
            index=dates,
        )

    rising = add_experimental_features(source(np.arange(40) + 100.0))
    falling = add_experimental_features(source(140.0 - np.arange(40)))
    flat = add_experimental_features(source(np.full(40, 100.0)))
    assert rising["rsi_14"].dropna().iloc[-1] == 100.0
    assert falling["rsi_14"].dropna().iloc[-1] == 0.0
    assert flat["rsi_14"].dropna().iloc[-1] == 50.0


def test_experimental_features_do_not_produce_infinite_values():
    dates = pd.date_range("2020-01-01", periods=40, freq="D")
    frame = pd.DataFrame(
        {
            "close": 100.0,
            "high": 101.0,
            "low": 99.0,
            "volume": 0.0,
            "distance_ma20": np.nan,
            "natr_20": 0.0,
            "volume_ratio_20": np.nan,
        },
        index=dates,
    )
    result = add_experimental_features(frame)
    values = result.loc[:, list(EXPERIMENTAL_FEATURES)].to_numpy(dtype=float)
    assert np.isfinite(values[~np.isnan(values)]).all()
