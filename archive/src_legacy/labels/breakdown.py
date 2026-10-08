"""Leakage-safe structural-breakdown labels.

The V6 target treats a breakdown as a competing event: a severe drawdown must
be accompanied by a persistent, confirmed down-trend.  This module exposes the
same idea as a fixed-horizon label so it can be used by H60/H120 risk heads.
It intentionally keeps the event date and the label end date in the output;
downstream split code must purge on ``label_end_date``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml


@dataclass(frozen=True)
class BreakdownLabelConfig:
    """Configuration for a fixed-horizon structural-breakdown event."""

    label_version: str
    horizon: int
    entry_lag: int = 1
    structural_failure_drawdown: float = -0.35
    failure_max_return_60: float = -0.15
    failure_max_slope_60: float = -0.0008
    failure_min_r2_60: float = 0.20
    minimum_observed_ratio_60: float = 0.90
    minimum_future_coverage: float = 0.90
    sampling_stride: int = 1

    @classmethod
    def from_yaml(cls, path: Path) -> BreakdownLabelConfig:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        target = payload["breakdown_target"]
        quality = payload["data_quality"]
        config = cls(
            label_version=str(payload["label_version"]),
            horizon=int(payload["horizon"]),
            entry_lag=int(payload.get("entry_lag", 1)),
            structural_failure_drawdown=float(target["structural_failure_drawdown"]),
            failure_max_return_60=float(target["failure_max_return_60"]),
            failure_max_slope_60=float(target["failure_max_slope_60"]),
            failure_min_r2_60=float(target["failure_min_r2_60"]),
            minimum_observed_ratio_60=float(target["minimum_observed_ratio_60"]),
            minimum_future_coverage=float(quality["minimum_future_coverage"]),
            sampling_stride=int(quality.get("sampling_stride", 1)),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if self.horizon <= 0 or self.entry_lag != 1:
            raise ValueError("Breakdown requires a positive horizon and entry_lag=1.")
        if not self.structural_failure_drawdown < 0:
            raise ValueError("structural_failure_drawdown must be negative.")
        if not self.failure_max_return_60 < 0:
            raise ValueError("failure_max_return_60 must be negative.")
        if not self.failure_max_slope_60 < 0:
            raise ValueError("failure_max_slope_60 must be negative.")
        if self.failure_min_r2_60 < 0:
            raise ValueError("failure_min_r2_60 cannot be negative.")
        if not 0 < self.minimum_observed_ratio_60 <= 1:
            raise ValueError("minimum_observed_ratio_60 must be in (0, 1].")
        if not 0 < self.minimum_future_coverage <= 1:
            raise ValueError("minimum_future_coverage must be in (0, 1].")
        if self.sampling_stride <= 0:
            raise ValueError("sampling_stride must be positive.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "label_version": self.label_version,
            "horizon": self.horizon,
            "entry_lag": self.entry_lag,
            "breakdown_target": {
                "structural_failure_drawdown": self.structural_failure_drawdown,
                "failure_max_return_60": self.failure_max_return_60,
                "failure_max_slope_60": self.failure_max_slope_60,
                "failure_min_r2_60": self.failure_min_r2_60,
                "minimum_observed_ratio_60": self.minimum_observed_ratio_60,
            },
            "data_quality": {
                "minimum_future_coverage": self.minimum_future_coverage,
                "sampling_stride": self.sampling_stride,
            },
        }


def _trend_metrics(values: np.ndarray) -> tuple[float, float, float]:
    """Return trailing return, log-price slope and R2."""
    finite = np.isfinite(values) & (values > 0)
    if finite.sum() < 2:
        return (np.nan, np.nan, np.nan)
    first = int(np.flatnonzero(finite)[0])
    last = int(np.flatnonzero(finite)[-1])
    trailing_return = float(values[last] / values[first] - 1.0)
    x = np.arange(len(values), dtype=float)[finite]
    y = np.log(values[finite])
    if len(y) < 2 or np.allclose(y, y[0]):
        return (trailing_return, 0.0, 0.0)
    slope, intercept = np.polyfit(x, y, 1)
    predicted = slope * x + intercept
    residual = float(np.sum((y - predicted) ** 2))
    total = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 if total == 0.0 else max(0.0, 1.0 - residual / total)
    return (trailing_return, float(slope), float(r2))


def label_breakdown_symbol(
    symbol: str,
    stock_ohlcv: pd.DataFrame,
    feature_ready: pd.Series,
    config: BreakdownLabelConfig,
    confirmed_wave: pd.Series | None = None,
) -> pd.DataFrame:
    """Create one row per symbol/date for a fixed-horizon breakdown label.

    ``confirmed_wave`` is optional.  When supplied, a wave event before a
    breakdown makes the row a non-breakdown outcome.  Without it, the label is
    a standalone breakdown-risk target.  Corporate-action and abnormal-volume
    masks should be included in ``confirmed_wave`` or applied upstream, because
    this low-level function only receives OHLCV and readiness information.
    """

    config.validate()
    required = {"date", "open", "close"}
    missing = sorted(required - set(stock_ohlcv.columns))
    if missing:
        raise ValueError(f"stock_ohlcv is missing columns: {missing}")
    stock = stock_ohlcv.copy()
    stock["date"] = pd.to_datetime(stock["date"], errors="raise")
    stock = stock.sort_values("date", kind="stable").drop_duplicates("date")
    dates = pd.DatetimeIndex(stock["date"], name="date")
    opens = stock["open"].to_numpy(dtype=float)
    closes = stock["close"].to_numpy(dtype=float)
    n = len(stock)

    ready = feature_ready.copy()
    ready.index = pd.to_datetime(ready.index)
    ready_values = ready.reindex(dates, fill_value=False).astype(bool).to_numpy()
    wave_values: np.ndarray | None = None
    if confirmed_wave is not None:
        wave = confirmed_wave.copy()
        wave.index = pd.to_datetime(wave.index)
        wave_values = wave.reindex(dates, fill_value=False).astype(bool).to_numpy()

    rows = pd.DataFrame({"symbol": symbol, "date": dates})
    rows["label_version"] = config.label_version
    rows["label_status"] = "censored_insufficient_future"
    rows["y_breakdown"] = pd.Series(pd.NA, index=rows.index, dtype="Int8")
    rows["sample_weight"] = np.nan
    rows["entry_date"] = pd.NaT
    rows["label_end_date"] = pd.NaT
    rows["breakdown_event_date"] = pd.NaT
    rows["entry_price"] = np.nan
    rows["breakdown_return"] = np.nan
    rows["trend_return_60"] = np.nan
    rows["trend_slope_60"] = np.nan
    rows["trend_r2_60"] = np.nan
    rows["future_coverage"] = np.nan

    for feature_idx in range(n):
        if not ready_values[feature_idx] or feature_idx + config.entry_lag >= n:
            continue
        if feature_idx % config.sampling_stride != 0:
            rows.loc[feature_idx, "label_status"] = "overlap_stride_excluded"
            continue
        entry_idx = feature_idx + config.entry_lag
        entry = opens[entry_idx]
        end_idx = min(n, entry_idx + config.horizon)
        future = closes[entry_idx:end_idx]
        coverage = float(np.isfinite(future).mean()) if len(future) else 0.0
        rows.loc[feature_idx, "entry_date"] = dates[entry_idx]
        rows.loc[feature_idx, "label_end_date"] = dates[end_idx - 1] if end_idx else pd.NaT
        rows.loc[feature_idx, "entry_price"] = entry
        rows.loc[feature_idx, "future_coverage"] = coverage
        if end_idx - entry_idx < config.horizon or not np.isfinite(entry) or entry <= 0:
            continue
        if coverage < config.minimum_future_coverage:
            rows.loc[feature_idx, "label_status"] = "censored_invalid_path"
            continue

        event = None
        event_idx = None
        event_return = np.nan
        trend = (np.nan, np.nan, np.nan)
        for offset, close in enumerate(future):
            absolute_idx = entry_idx + offset
            if not np.isfinite(close) or close <= 0:
                continue
            if wave_values is not None and wave_values[absolute_idx]:
                event = "wave"
                event_idx = absolute_idx
                break
            drawdown_from_entry = close / entry - 1.0
            if drawdown_from_entry > config.structural_failure_drawdown:
                continue
            start = max(0, absolute_idx - 59)
            trend = _trend_metrics(closes[start : absolute_idx + 1])
            observed_ratio = float(np.isfinite(closes[start : absolute_idx + 1]).mean())
            confirmed = (
                trend[0] <= config.failure_max_return_60
                and trend[1] <= config.failure_max_slope_60
                and trend[2] >= config.failure_min_r2_60
                and observed_ratio >= config.minimum_observed_ratio_60
            )
            if confirmed:
                event = "breakdown"
                event_idx = absolute_idx
                event_return = float(drawdown_from_entry)
                break

        rows.loc[feature_idx, "trend_return_60"] = trend[0]
        rows.loc[feature_idx, "trend_slope_60"] = trend[1]
        rows.loc[feature_idx, "trend_r2_60"] = trend[2]
        if event == "breakdown":
            rows.loc[feature_idx, "y_breakdown"] = 1
            rows.loc[feature_idx, "sample_weight"] = 1.0
            rows.loc[feature_idx, "label_status"] = "breakdown"
            rows.loc[feature_idx, "breakdown_event_date"] = dates[event_idx]
            rows.loc[feature_idx, "breakdown_return"] = event_return
        elif event == "wave":
            rows.loc[feature_idx, "y_breakdown"] = 0
            rows.loc[feature_idx, "sample_weight"] = 1.0
            rows.loc[feature_idx, "label_status"] = "wave_before_breakdown"
        else:
            rows.loc[feature_idx, "y_breakdown"] = 0
            rows.loc[feature_idx, "sample_weight"] = 1.0
            rows.loc[feature_idx, "label_status"] = "no_breakdown_in_horizon"

    rows.loc[~ready_values, "label_status"] = "feature_not_ready"
    rows.loc[~ready_values, ["y_breakdown", "sample_weight"]] = [pd.NA, np.nan]
    return rows
