import numpy as np
import pandas as pd

from src.labels import BreakdownLabelConfig, label_breakdown_symbol


def make_config() -> BreakdownLabelConfig:
    return BreakdownLabelConfig(
        label_version="test",
        horizon=70,
        structural_failure_drawdown=-0.35,
        failure_max_return_60=-0.15,
        failure_max_slope_60=-0.0008,
        failure_min_r2_60=0.20,
        minimum_observed_ratio_60=0.90,
        minimum_future_coverage=1.0,
        sampling_stride=1,
    )


def make_stock(periods: int = 90) -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", periods=periods, freq="D")
    close = np.linspace(100.0, 45.0, periods)
    return pd.DataFrame(
        {
            "date": dates,
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": 1_000.0,
        }
    )


def test_breakdown_requires_drawdown_and_confirmed_trend() -> None:
    stock = make_stock()
    labels = label_breakdown_symbol(
        "AAA",
        stock,
        pd.Series(True, index=stock["date"]),
        make_config(),
    )
    assert labels["y_breakdown"].eq(1).any()
    assert labels.loc[labels["y_breakdown"].eq(1), "breakdown_event_date"].notna().all()
    assert labels.loc[labels["y_breakdown"].eq(1), "trend_r2_60"].ge(0.20).all()


def test_wave_before_breakdown_is_not_a_breakdown() -> None:
    stock = make_stock()
    wave = pd.Series(False, index=stock["date"])
    wave.iloc[10] = True
    labels = label_breakdown_symbol(
        "AAA",
        stock,
        pd.Series(True, index=stock["date"]),
        make_config(),
        confirmed_wave=wave,
    )
    assert labels.iloc[0]["y_breakdown"] == 0
    assert labels.iloc[0]["label_status"] == "wave_before_breakdown"


def test_breakdown_censors_short_future_paths() -> None:
    stock = make_stock(periods=20)
    labels = label_breakdown_symbol(
        "AAA",
        stock,
        pd.Series(True, index=stock["date"]),
        make_config(),
    )
    assert labels["y_breakdown"].isna().any()
