"""Leakage-safe medium-horizon continuation labels.

Continuation is deliberately independent from the H20 surge label: a stock can
be positive here without first producing a rapid surge.  The label is a
volatility-scaled excess-return and drawdown outcome over a configured horizon.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from numpy.lib.stride_tricks import sliding_window_view

EVENT_ID_SCHEME = "sha256(label_version|symbol|entry_date|label_end_date)"


def continuation_event_id(
    label_version: str,
    symbol: str,
    entry_date: pd.Timestamp,
    label_end_date: pd.Timestamp,
) -> str:
    """Return a stable, opaque identity for one labeled continuation interval."""
    entry = pd.Timestamp(entry_date).strftime("%Y-%m-%d")
    end = pd.Timestamp(label_end_date).strftime("%Y-%m-%d")
    canonical = "|".join((str(label_version), str(symbol), entry, end))
    return f"sha256:{sha256(canonical.encode('utf-8')).hexdigest()}"


def attach_continuation_weight_components(
    rows: pd.DataFrame,
    *,
    class_balance_mode: str = "none",
    include_date_balance: bool = True,
) -> pd.DataFrame:
    """Attach causal interval/date/class weight components to labeled rows.

    ``rows`` must be the training slice when class balancing is enabled.  This
    prevents class prevalence from leaking information from future folds.
    Interval uniqueness and daily row counts use only sample metadata.
    """
    if class_balance_mode not in {"none", "full_ratio", "sqrt_ratio"}:
        raise ValueError("class_balance_mode must be none, full_ratio, or sqrt_ratio.")
    required = {"symbol", "date", "entry_date", "label_end_date", "y_entry"}
    missing = sorted(required.difference(rows.columns))
    if missing:
        raise ValueError(f"Missing columns for continuation weights: {missing}")
    result = rows.copy()
    columns = (
        "event_concurrency_mean",
        "event_uniqueness_weight",
        "date_balance_weight",
        "class_balance_weight",
        "sample_weight_final",
    )
    for column in columns:
        result[column] = np.nan
    labeled = result["y_entry"].notna()
    if not labeled.any():
        return result
    event_rows = result.loc[labeled].copy()
    for column in ("date", "entry_date", "label_end_date"):
        event_rows[column] = pd.to_datetime(event_rows[column], errors="raise")
    if event_rows["entry_date"].gt(event_rows["label_end_date"]).any():
        raise ValueError("Continuation events cannot end before their entry date.")
    calendar = pd.DatetimeIndex(
        pd.to_datetime(result["date"], errors="raise").drop_duplicates().sort_values()
    )
    start_position = calendar.get_indexer(event_rows["entry_date"])
    end_position = calendar.get_indexer(event_rows["label_end_date"])
    if (start_position < 0).any() or (end_position < 0).any():
        raise ValueError("Event boundaries must exist in the decision-date calendar.")
    uniqueness = np.empty(len(event_rows), dtype=float)
    mean_concurrency = np.empty(len(event_rows), dtype=float)
    event_rows["_start_position"] = start_position
    event_rows["_end_position"] = end_position
    for _, group in event_rows.groupby("symbol", sort=False):
        starts = group["_start_position"].to_numpy(dtype=int)
        ends = group["_end_position"].to_numpy(dtype=int)
        delta = np.zeros(len(calendar) + 1, dtype=int)
        np.add.at(delta, starts, 1)
        np.add.at(delta, ends + 1, -1)
        concurrency = np.cumsum(delta[:-1])
        inverse_concurrency = np.divide(
            1.0,
            concurrency,
            out=np.zeros_like(concurrency, dtype=float),
            where=concurrency > 0,
        )
        inverse_cumulative = np.concatenate(([0.0], np.cumsum(inverse_concurrency)))
        concurrency_cumulative = np.concatenate(([0.0], np.cumsum(concurrency)))
        group_uniqueness = (
            inverse_cumulative[ends + 1] - inverse_cumulative[starts]
        ) / (ends - starts + 1)
        group_mean_concurrency = (
            concurrency_cumulative[ends + 1] - concurrency_cumulative[starts]
        ) / (ends - starts + 1)
        positions = event_rows.index.get_indexer(group.index)
        uniqueness[positions] = group_uniqueness
        mean_concurrency[positions] = group_mean_concurrency
    event_rows["event_concurrency_mean"] = mean_concurrency
    event_rows["event_uniqueness_weight"] = uniqueness
    event_rows["event_uniqueness_weight"] /= event_rows[
        "event_uniqueness_weight"
    ].mean()
    if include_date_balance:
        date_counts = event_rows.groupby("date", observed=True)["symbol"].transform("size")
        event_rows["date_balance_weight"] = (
            len(event_rows) / event_rows["date"].nunique() / date_counts
        )
    else:
        event_rows["date_balance_weight"] = 1.0
    event_rows["class_balance_weight"] = 1.0
    if class_balance_mode != "none":
        positive = event_rows["y_entry"].astype(int).eq(1)
        positive_rows = int(positive.sum())
        negative_rows = int((~positive).sum())
        if not positive_rows or not negative_rows:
            raise ValueError("Class balancing requires both positive and negative labeled rows.")
        ratio = negative_rows / positive_rows
        if class_balance_mode == "sqrt_ratio":
            ratio = float(np.sqrt(ratio))
        event_rows.loc[positive, "class_balance_weight"] = ratio
    final = (
        event_rows["event_uniqueness_weight"]
        * event_rows["date_balance_weight"]
        * event_rows["class_balance_weight"]
    )
    event_rows["sample_weight_final"] = final / final.mean()
    result.loc[event_rows.index, list(columns)] = event_rows.loc[:, list(columns)]
    return result


@dataclass(frozen=True)
class ContinuationLabelConfig:
    label_version: str
    horizon: int
    entry_lag: int
    volatility_lookback: int
    annualization_factor: int
    excess_volatility_multiplier: float
    minimum_excess_return: float
    minimum_terminal_return: float
    maximum_drawdown: float
    minimum_future_coverage: float
    minimum_volatility_observations: int
    sampling_stride: int = 1
    return_type: str = "simple"

    @classmethod
    def from_yaml(cls, path: Path) -> ContinuationLabelConfig:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        target = payload["continuation_target"]
        quality = payload["data_quality"]
        config = cls(
            label_version=str(payload["label_version"]),
            horizon=int(payload["horizon"]),
            entry_lag=int(payload.get("entry_lag", 1)),
            volatility_lookback=int(payload["volatility_lookback"]),
            annualization_factor=int(payload.get("annualization_factor", 252)),
            excess_volatility_multiplier=float(target["excess_volatility_multiplier"]),
            minimum_excess_return=float(target["minimum_excess_return"]),
            minimum_terminal_return=float(target["minimum_terminal_return"]),
            maximum_drawdown=float(target["maximum_drawdown"]),
            minimum_future_coverage=float(quality["minimum_future_coverage"]),
            minimum_volatility_observations=int(quality["minimum_volatility_observations"]),
            sampling_stride=int(quality.get("sampling_stride", 1)),
            return_type=str(target.get("return_type", "simple")),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if self.entry_lag != 1 or self.horizon <= 0:
            raise ValueError("Continuation requires entry_lag=1 and a positive horizon.")
        if self.volatility_lookback <= 1 or self.minimum_volatility_observations <= 1:
            raise ValueError("Volatility lookback and minimum observations must exceed one.")
        if self.excess_volatility_multiplier < 0 or self.minimum_excess_return < 0:
            raise ValueError("Continuation return thresholds must be non-negative.")
        if self.maximum_drawdown >= 0:
            raise ValueError("maximum_drawdown must be negative.")
        if not 0 < self.minimum_future_coverage <= 1:
            raise ValueError("minimum_future_coverage must be in (0, 1].")
        if self.sampling_stride <= 0:
            raise ValueError("sampling_stride must be positive.")
        if self.return_type != "simple":
            raise ValueError("Only simple returns are supported for continuation labels.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "label_version": self.label_version,
            "horizon": self.horizon,
            "entry_lag": self.entry_lag,
            "volatility_lookback": self.volatility_lookback,
            "annualization_factor": self.annualization_factor,
            "continuation_target": {
                "return_type": self.return_type,
                "excess_volatility_multiplier": self.excess_volatility_multiplier,
                "minimum_excess_return": self.minimum_excess_return,
                "minimum_terminal_return": self.minimum_terminal_return,
                "maximum_drawdown": self.maximum_drawdown,
            },
            "data_quality": {
                "minimum_future_coverage": self.minimum_future_coverage,
                "minimum_volatility_observations": self.minimum_volatility_observations,
                "sampling_stride": self.sampling_stride,
            },
        }


def label_continuation_symbol(
    symbol: str,
    stock_ohlcv: pd.DataFrame,
    vnindex_ohlcv: pd.DataFrame,
    feature_ready: pd.Series,
    config: ContinuationLabelConfig,
) -> pd.DataFrame:
    """Return one independent continuation row per symbol/date."""
    config.validate()
    stock = stock_ohlcv.copy()
    market = vnindex_ohlcv.copy()
    stock["date"] = pd.to_datetime(stock["date"], errors="raise")
    market["date"] = pd.to_datetime(market["date"], errors="raise")
    calendar = pd.DatetimeIndex(market["date"].sort_values().unique(), name="date")
    stock = stock.set_index("date").reindex(calendar)
    market = market.set_index("date").reindex(calendar)
    close = stock["close"].to_numpy(dtype=float)
    open_price = stock["open"].to_numpy(dtype=float)
    volume = stock["volume"].to_numpy(dtype=float)
    market_close = market["close"].to_numpy(dtype=float)
    market_open = market["open"].to_numpy(dtype=float)
    n = len(calendar)
    rows = pd.DataFrame({"date": calendar})
    rows.insert(0, "symbol", symbol)
    rows["label_version"] = config.label_version
    rows["label_status"] = "censored_insufficient_future"
    rows["y_entry"] = pd.Series(pd.NA, index=rows.index, dtype="Int8")
    rows["y_strength"] = np.nan
    rows["sample_weight"] = np.nan
    rows["event_id"] = pd.Series(pd.NA, index=rows.index, dtype="string")
    rows["event_start_date"] = pd.NaT
    rows["entry_date"] = pd.NaT
    rows["label_end_date"] = pd.NaT
    rows["entry_price"] = np.nan
    rows["terminal_return"] = np.nan
    rows["excess_market_return"] = np.nan
    rows["maximum_drawdown"] = np.nan
    rows["future_coverage"] = np.nan
    rows["target_return"] = np.nan
    log_return = np.log(pd.Series(close, index=calendar).where(lambda value: value > 0)).diff()
    annualized_volatility = (
        log_return.rolling(
            config.volatility_lookback,
            min_periods=config.minimum_volatility_observations,
        ).std(ddof=0)
        * np.sqrt(config.annualization_factor)
    ).to_numpy()
    evaluable = max(0, n - config.horizon)
    if evaluable:
        path_close = sliding_window_view(close[1:], config.horizon)
        path_market_close = sliding_window_view(market_close[1:], config.horizon)
        entry = open_price[1 : evaluable + 1]
        market_entry = market_open[1 : evaluable + 1]
        with np.errstate(divide="ignore", invalid="ignore"):
            path_return = path_close / entry[:, None] - 1.0
            market_return_path = path_market_close / market_entry[:, None] - 1.0
        finite = (
            np.isfinite(path_return)
            & np.isfinite(market_return_path)
            & (path_close > 0)
            & (path_market_close > 0)
        )
        coverage = finite.mean(axis=1)
        path_return = np.where(finite, path_return, np.nan)
        market_return_path = np.where(finite, market_return_path, np.nan)
        terminal_return = path_return[:, -1]
        excess_return = terminal_return - market_return_path[:, -1]
        path_with_zero = np.concatenate(
            [np.zeros((evaluable, 1), dtype=float), path_return], axis=1
        )
        peak_input = np.where(np.isfinite(path_with_zero), 1.0 + path_with_zero, -np.inf)
        running_peak = np.maximum.accumulate(peak_input, axis=1)
        drawdown_path = np.where(
            np.isfinite(path_with_zero),
            (1.0 + path_with_zero) / running_peak - 1.0,
            np.nan,
        )
        drawdown = np.nanmin(drawdown_path, axis=1)
        volatility = annualized_volatility[:evaluable]
        horizon_volatility = volatility * np.sqrt(config.horizon / config.annualization_factor)
        target_return = np.maximum(
            config.minimum_excess_return,
            config.excess_volatility_multiplier * horizon_volatility,
        )
        path_valid = (
            np.isfinite(entry)
            & (entry > 0)
            & np.isfinite(volume[1 : evaluable + 1])
            & (volume[1 : evaluable + 1] > 0)
            & np.isfinite(market_entry)
            & (market_entry > 0)
            & np.isfinite(volatility)
            & (coverage >= config.minimum_future_coverage)
            & np.isfinite(terminal_return)
            & np.isfinite(excess_return)
            & np.isfinite(drawdown)
        )
        sampled = np.arange(evaluable) % config.sampling_stride == 0
        valid = path_valid & sampled
        positive = valid & (excess_return >= target_return) & (
            terminal_return >= config.minimum_terminal_return
        ) & (drawdown >= config.maximum_drawdown)
        quality = np.clip(
            excess_return / np.maximum(target_return, np.finfo(float).eps), 0, 2
        ) / 2
        quality *= np.clip(1 + drawdown / abs(config.maximum_drawdown), 0, 1)
        rows.loc[: evaluable - 1, "entry_date"] = calendar[1 : evaluable + 1].to_numpy()
        rows.loc[: evaluable - 1, "label_end_date"] = calendar[config.horizon :].to_numpy()
        rows.loc[: evaluable - 1, "entry_price"] = entry
        rows.loc[: evaluable - 1, "terminal_return"] = terminal_return
        rows.loc[: evaluable - 1, "excess_market_return"] = excess_return
        rows.loc[: evaluable - 1, "maximum_drawdown"] = drawdown
        rows.loc[: evaluable - 1, "future_coverage"] = coverage
        rows.loc[: evaluable - 1, "target_return"] = target_return
        rows.loc[: evaluable - 1, "label_status"] = np.where(
            ~sampled,
            "overlap_stride_excluded",
            np.where(path_valid, np.where(positive, "positive", "negative"), "censored_invalid_path"),
        )
        rows.loc[: evaluable - 1, "y_entry"] = pd.Series(
            np.where(valid, positive.astype("int8"), pd.NA), dtype="Int8"
        ).to_numpy()
        rows.loc[: evaluable - 1, "sample_weight"] = np.where(valid, 1.0, np.nan)
        rows.loc[: evaluable - 1, "y_strength"] = np.where(positive, np.clip(quality, 0, 1), np.nan)
    ready = feature_ready.copy()
    ready.index = pd.to_datetime(ready.index)
    not_ready = ~ready.reindex(calendar, fill_value=False).astype(bool).to_numpy()
    rows.loc[not_ready, "label_status"] = "feature_not_ready"
    rows.loc[not_ready, ["y_entry", "y_strength", "sample_weight"]] = [pd.NA, np.nan, np.nan]
    rows.loc[rows["y_entry"].isna(), "label_status"] = rows.loc[
        rows["y_entry"].isna(), "label_status"
    ].replace("negative", "censored_insufficient_future")
    labeled = rows["y_entry"].notna()
    rows.loc[labeled, "event_start_date"] = rows.loc[labeled, "entry_date"].to_numpy()
    rows.loc[labeled, "event_id"] = [
        continuation_event_id(label_version, event_symbol, entry_date, label_end_date)
        for label_version, event_symbol, entry_date, label_end_date in zip(
            rows.loc[labeled, "label_version"],
            rows.loc[labeled, "symbol"],
            rows.loc[labeled, "entry_date"],
            rows.loc[labeled, "label_end_date"],
            strict=True,
        )
    ]
    return rows
