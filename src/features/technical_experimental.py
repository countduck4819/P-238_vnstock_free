"""Compact, causal technical feature candidates for ablation experiments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

EXPERIMENTAL_GROUPS: dict[str, tuple[str, ...]] = {
    "temporal_change": (
        "return_1d_simple",
        "return_3d",
        "return_5d",
        "return_1d_minus_avg_5d",
    ),
    "trend_signal": ("distance_ma10", "above_ma20_state"),
    "rsi_signal": ("rsi_14", "rsi_change_3", "rsi_zone"),
    "macd_signal": ("macd_hist_atr", "macd_hist_change_3", "macd_hist_state"),
    "volume_flow": (
        "volume_ratio_5",
        "volume_ratio_20_change_3",
        "signed_money_flow_ratio_20",
    ),
}

EXPERIMENTAL_FEATURES = tuple(
    feature for group in EXPERIMENTAL_GROUPS.values() for feature in group
)


@dataclass(frozen=True)
class ExperimentalFeatureConfig:
    """Versioned parameters for the compact candidate feature pack."""

    return_windows: tuple[int, ...] = (1, 3, 5)
    acceleration_window: int = 5
    moving_average_window: int = 10
    rsi_window: int = 14
    rsi_change_lag: int = 3
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    macd_change_lag: int = 3
    volume_ratio_window: int = 5
    volume_change_lag: int = 3
    money_flow_window: int = 20

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> ExperimentalFeatureConfig:
        payload = payload or {}
        returns = payload.get("returns", {})
        trend = payload.get("trend", {})
        rsi = payload.get("rsi", {})
        macd = payload.get("macd", {})
        volume = payload.get("volume", {})
        config = cls(
            return_windows=tuple(int(value) for value in returns.get("windows", (1, 3, 5))),
            acceleration_window=int(returns.get("acceleration_window", 5)),
            moving_average_window=int(trend.get("moving_average_window", 10)),
            rsi_window=int(rsi.get("window", 14)),
            rsi_change_lag=int(rsi.get("change_lag", 3)),
            rsi_oversold=float(rsi.get("oversold", 30)),
            rsi_overbought=float(rsi.get("overbought", 70)),
            macd_fast=int(macd.get("fast", 12)),
            macd_slow=int(macd.get("slow", 26)),
            macd_signal=int(macd.get("signal", 9)),
            macd_change_lag=int(macd.get("change_lag", 3)),
            volume_ratio_window=int(volume.get("ratio_window", 5)),
            volume_change_lag=int(volume.get("change_lag", 3)),
            money_flow_window=int(volume.get("money_flow_window", 20)),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if self.return_windows != (1, 3, 5) or self.acceleration_window != 5:
            raise ValueError("Experimental schema v2 requires return windows [1, 3, 5].")
        if self.moving_average_window != 10 or self.rsi_window != 14:
            raise ValueError("Experimental schema v2 requires MA10 and RSI14.")
        if not 0 <= self.rsi_oversold < self.rsi_overbought <= 100:
            raise ValueError("RSI zone thresholds are invalid.")
        if not 0 < self.macd_fast < self.macd_slow or self.macd_signal <= 0:
            raise ValueError("MACD windows are invalid.")
        if min(self.rsi_change_lag, self.macd_change_lag, self.volume_change_lag) <= 0:
            raise ValueError("Change lags must be positive.")
        if self.volume_ratio_window != 5 or self.money_flow_window != 20:
            raise ValueError("Experimental schema v2 requires volume ratio 5 and flow 20.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "returns": {"windows": list(self.return_windows), "acceleration_window": self.acceleration_window},
            "trend": {"moving_average_window": self.moving_average_window},
            "rsi": {
                "window": self.rsi_window,
                "change_lag": self.rsi_change_lag,
                "oversold": self.rsi_oversold,
                "overbought": self.rsi_overbought,
            },
            "macd": {
                "fast": self.macd_fast,
                "slow": self.macd_slow,
                "signal": self.macd_signal,
                "change_lag": self.macd_change_lag,
            },
            "volume": {
                "ratio_window": self.volume_ratio_window,
                "change_lag": self.volume_change_lag,
                "money_flow_window": self.money_flow_window,
            },
        }


def add_experimental_features(
    frame: pd.DataFrame,
    config: ExperimentalFeatureConfig | None = None,
) -> pd.DataFrame:
    """Add the paper-inspired candidate pack to an existing stock feature frame.

    The function only reads current and trailing values.  It deliberately adds
    a small set of level, change and signal representations rather than every
    available technical indicator.
    """
    config = config or ExperimentalFeatureConfig()
    config.validate()
    result = frame.copy()
    close = pd.to_numeric(result["close"], errors="coerce")
    volume = pd.to_numeric(result["volume"], errors="coerce")

    for window in config.return_windows:
        result[f"return_{window}d" if window > 1 else "return_1d_simple"] = (
            close / close.shift(window) - 1.0
        )
    result["return_1d_minus_avg_5d"] = (
        result["return_1d_simple"] - result["return_5d"] / config.acceleration_window
    )

    ma10 = close.rolling(config.moving_average_window, min_periods=8).mean()
    result["distance_ma10"] = close / ma10 - 1.0
    result["above_ma20_state"] = np.sign(result["distance_ma20"]).where(
        result["distance_ma20"].notna()
    )

    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    rsi_minimum_periods = max(2, int(np.ceil(config.rsi_window * 0.8)))
    average_gain = gain.rolling(config.rsi_window, min_periods=rsi_minimum_periods).mean()
    average_loss = loss.rolling(config.rsi_window, min_periods=rsi_minimum_periods).mean()
    relative_strength = average_gain / average_loss.replace(0, np.nan)
    result["rsi_14"] = 100.0 - 100.0 / (1.0 + relative_strength)
    enough_rsi = average_gain.notna() & average_loss.notna()
    result.loc[enough_rsi & average_loss.eq(0) & average_gain.gt(0), "rsi_14"] = 100.0
    result.loc[enough_rsi & average_gain.eq(0) & average_loss.gt(0), "rsi_14"] = 0.0
    result.loc[enough_rsi & average_gain.eq(0) & average_loss.eq(0), "rsi_14"] = 50.0
    result["rsi_14"] = result["rsi_14"].where(enough_rsi)
    result["rsi_change_3"] = result["rsi_14"].diff(config.rsi_change_lag)
    result["rsi_zone"] = np.select(
        [result["rsi_14"].lt(config.rsi_oversold), result["rsi_14"].gt(config.rsi_overbought)],
        [1.0, -1.0],
        default=0.0,
    )
    result.loc[result["rsi_14"].isna(), "rsi_zone"] = np.nan

    ema12 = close.ewm(span=config.macd_fast, adjust=False, min_periods=10).mean()
    ema26 = close.ewm(span=config.macd_slow, adjust=False, min_periods=21).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(
        span=config.macd_signal, adjust=False, min_periods=config.macd_signal
    ).mean()
    macd_hist = macd - macd_signal
    atr_scale = close * result["natr_20"]
    result["macd_hist_atr"] = macd_hist / atr_scale.replace(0, np.nan)
    result["macd_hist_change_3"] = result["macd_hist_atr"].diff(config.macd_change_lag)
    result["macd_hist_state"] = np.sign(macd_hist).where(macd_hist.notna())

    prior_volume_median_5 = volume.shift(1).rolling(config.volume_ratio_window, min_periods=4).median()
    result["volume_ratio_5"] = volume / prior_volume_median_5.replace(0, np.nan)
    result["volume_ratio_20_change_3"] = result["volume_ratio_20"].diff(config.volume_change_lag)
    typical_price = (result["high"] + result["low"] + close) / 3.0
    signed_flow = typical_price * volume * np.sign(typical_price.diff())
    flow_minimum_periods = max(2, int(np.ceil(config.money_flow_window * 0.8)))
    flow_window = signed_flow.rolling(
        config.money_flow_window, min_periods=flow_minimum_periods
    ).sum()
    absolute_flow = signed_flow.abs().rolling(
        config.money_flow_window, min_periods=flow_minimum_periods
    ).sum()
    result["signed_money_flow_ratio_20"] = flow_window / absolute_flow.replace(0, np.nan)

    numeric_columns = [
        "return_1d_simple",
        "return_3d",
        "return_5d",
        "return_1d_minus_avg_5d",
        "distance_ma10",
        "above_ma20_state",
        "rsi_14",
        "rsi_change_3",
        "rsi_zone",
        "macd_hist_atr",
        "macd_hist_change_3",
        "macd_hist_state",
        "volume_ratio_5",
        "volume_ratio_20_change_3",
        "signed_money_flow_ratio_20",
    ]
    result[numeric_columns] = result[numeric_columns].replace([np.inf, -np.inf], np.nan)
    return result
