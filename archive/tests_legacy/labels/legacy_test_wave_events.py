from __future__ import annotations

import numpy as np
import pandas as pd

from src.labels.wave_events import (
    WaveLabelConfig,
    _candidate_metrics,
    label_symbol,
)


def make_market(periods: int = 100) -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-01", periods=periods, name="date")
    close = np.linspace(1000, 1020, periods)
    return pd.DataFrame(
        {
            "date": dates,
            "open": close - 1,
            "high": close + 2,
            "low": close - 2,
            "close": close,
            "volume": 10_000_000,
        }
    )


def make_stock(direction: str, periods: int = 100) -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-01", periods=periods, name="date")
    close = np.full(periods, 100.0)
    if direction == "up":
        close[51:71] = np.linspace(100, 115, 20)
        close[71:] = 115
    elif direction == "down":
        close[51:71] = np.linspace(100, 90, 20)
        close[71:] = 90
    return pd.DataFrame(
        {
            "date": dates,
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": 1_000_000,
        }
    )


def candidate_frame(direction: str) -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    stock = make_stock(direction)
    market = make_market()
    calendar = pd.DatetimeIndex(market["date"], name="date")
    aligned = stock.set_index("date")
    market_aligned = market.set_index("date")
    ready = pd.Series(True, index=calendar)
    return (
        _candidate_metrics(aligned, market_aligned, ready, WaveLabelConfig()),
        calendar,
    )


def test_upward_path_creates_positive_candidate_and_bounded_strength() -> None:
    candidates, calendar = candidate_frame("up")
    target = candidates.set_index("date").loc[calendar[50]]

    assert target["candidate_label"] == 1
    assert target["label_status"] == "candidate_positive"
    assert 0 <= target["candidate_strength"] <= 1
    assert target["time_to_upper"] == 12
    assert pd.isna(target["time_to_lower"])


def test_downward_path_creates_clean_negative() -> None:
    candidates, calendar = candidate_frame("down")
    target = candidates.set_index("date").loc[calendar[50]]

    assert target["candidate_label"] == 0
    assert target["label_status"] == "negative"
    assert target["time_to_lower"] == 9
    assert pd.isna(target["time_to_upper"])


def test_last_horizon_is_censored() -> None:
    candidates, _ = candidate_frame("up")
    tail = candidates.tail(WaveLabelConfig().horizon)

    assert tail["label_status"].eq("censored_insufficient_future").all()
    assert tail["candidate_label"].isna().all()


def test_event_clustering_limits_ignition_labels() -> None:
    stock = make_stock("up")
    market = make_market()
    ready = pd.Series(True, index=pd.DatetimeIndex(market["date"]))
    labels, events = label_symbol("AAA", stock, market, ready, WaveLabelConfig())

    assert not events.empty
    assert labels["y_entry"].eq(1).sum() <= len(events) * WaveLabelConfig().ignition_width
    assert labels.loc[labels["y_entry"].eq(1), "y_strength"].between(0, 1).all()
    assert labels.loc[labels["y_entry"].eq(0), "y_strength"].isna().all()
