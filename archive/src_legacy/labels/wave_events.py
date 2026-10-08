"""Wave Event Engine for trend-onset classification and strength labels."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from numpy.lib.stride_tricks import sliding_window_view


@dataclass(frozen=True)
class WaveLabelConfig:
    """Versioned parameters for Wave Event detection and labeling."""

    label_version: str = "wave_label_v1"
    entry_lag: int = 1
    horizon: int = 20
    volatility_lookback: int = 20
    annualization_factor: int = 252
    upper_volatility_multiplier: float = 1.0
    upper_minimum: float = 0.08
    upper_maximum: float = 0.20
    lower_volatility_multiplier: float = 0.5
    lower_minimum: float = 0.04
    lower_maximum: float = 0.10
    max_time_to_upper: int = 15
    minimum_terminal_fraction: float = 0.5
    minimum_persistence: float = 0.5
    minimum_future_coverage: float = 0.9
    minimum_volatility_observations: int = 16
    event_maximum_gap: int = 5
    ignition_width: int = 3
    cooldown: int = 20

    @classmethod
    def from_yaml(cls, path: Path) -> WaveLabelConfig:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls(
            label_version=payload["label_version"],
            entry_lag=int(payload["entry_lag"]),
            horizon=int(payload["horizon"]),
            volatility_lookback=int(payload["volatility_lookback"]),
            annualization_factor=int(payload.get("annualization_factor", 252)),
            upper_volatility_multiplier=float(
                payload["upper_barrier"]["volatility_multiplier"]
            ),
            upper_minimum=float(payload["upper_barrier"]["minimum"]),
            upper_maximum=float(payload["upper_barrier"]["maximum"]),
            lower_volatility_multiplier=float(
                payload["lower_barrier"]["volatility_multiplier"]
            ),
            lower_minimum=float(payload["lower_barrier"]["minimum"]),
            lower_maximum=float(payload["lower_barrier"]["maximum"]),
            max_time_to_upper=int(payload["positive_rules"]["max_time_to_upper"]),
            minimum_terminal_fraction=float(
                payload["positive_rules"]["minimum_terminal_fraction"]
            ),
            minimum_persistence=float(
                payload["positive_rules"]["minimum_persistence"]
            ),
            minimum_future_coverage=float(
                payload["data_quality"]["minimum_future_coverage"]
            ),
            minimum_volatility_observations=int(
                payload["data_quality"]["minimum_volatility_observations"]
            ),
            event_maximum_gap=int(payload["event_clustering"]["maximum_gap"]),
            ignition_width=int(payload["event_clustering"]["ignition_width"]),
            cooldown=int(payload["event_clustering"]["cooldown"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "label_version": self.label_version,
            "entry_lag": self.entry_lag,
            "horizon": self.horizon,
            "volatility_lookback": self.volatility_lookback,
            "annualization_factor": self.annualization_factor,
            "upper_barrier": {
                "volatility_multiplier": self.upper_volatility_multiplier,
                "minimum": self.upper_minimum,
                "maximum": self.upper_maximum,
            },
            "lower_barrier": {
                "volatility_multiplier": self.lower_volatility_multiplier,
                "minimum": self.lower_minimum,
                "maximum": self.lower_maximum,
            },
            "positive_rules": {
                "max_time_to_upper": self.max_time_to_upper,
                "minimum_terminal_fraction": self.minimum_terminal_fraction,
                "minimum_persistence": self.minimum_persistence,
            },
            "data_quality": {
                "minimum_future_coverage": self.minimum_future_coverage,
                "minimum_volatility_observations": self.minimum_volatility_observations,
            },
            "event_clustering": {
                "maximum_gap": self.event_maximum_gap,
                "ignition_width": self.ignition_width,
                "cooldown": self.cooldown,
            },
        }


def _first_true(mask: np.ndarray) -> np.ndarray:
    any_true = mask.any(axis=1)
    first = mask.argmax(axis=1).astype(float) + 1.0
    first[~any_true] = np.inf
    return first


def _safe_row_max(values: np.ndarray) -> np.ndarray:
    result = np.where(np.isfinite(values), values, -np.inf).max(axis=1)
    result[np.isneginf(result)] = np.nan
    return result


def _safe_row_min(values: np.ndarray) -> np.ndarray:
    result = np.where(np.isfinite(values), values, np.inf).min(axis=1)
    result[np.isposinf(result)] = np.nan
    return result


def _sigmoid(values: np.ndarray) -> np.ndarray:
    clipped = np.clip(values, -30, 30)
    return 1.0 / (1.0 + np.exp(-clipped))


def _candidate_metrics(
    aligned: pd.DataFrame,
    market: pd.DataFrame,
    feature_ready: pd.Series,
    config: WaveLabelConfig,
) -> pd.DataFrame:
    if config.entry_lag != 1:
        raise ValueError("wave_label_v1 currently requires entry_lag=1")

    calendar = aligned.index
    row_count = len(calendar)
    horizon = config.horizon
    evaluable_count = max(0, row_count - horizon)

    output = pd.DataFrame(index=calendar)
    output.index.name = "date"
    output["_calendar_position"] = np.arange(row_count)
    current_observed = aligned[["open", "high", "low", "close", "volume"]].notna().all(axis=1)
    output["_current_observed"] = current_observed
    output["label_status"] = "censored_insufficient_future"
    output["candidate_label"] = pd.Series(pd.NA, index=calendar, dtype="Int8")

    metric_columns = [
        "entry_price",
        "upper_barrier",
        "lower_barrier",
        "volatility_at_t",
        "mfe",
        "mae",
        "terminal_return",
        "market_return",
        "excess_market_return",
        "time_to_upper",
        "time_to_lower",
        "persistence",
        "trend_efficiency",
        "future_coverage",
        "candidate_strength",
    ]
    for column in metric_columns:
        output[column] = np.nan
    output["entry_date"] = pd.NaT
    output["label_end_date"] = pd.NaT
    output["peak_date"] = pd.NaT

    if evaluable_count == 0:
        return output.loc[current_observed].reset_index()

    close = aligned["close"].to_numpy(dtype=float)
    open_price = aligned["open"].to_numpy(dtype=float)
    volume = aligned["volume"].to_numpy(dtype=float)
    market_open = market["open"].reindex(calendar).to_numpy(dtype=float)
    market_close = market["close"].reindex(calendar).to_numpy(dtype=float)

    log_close = np.log(pd.Series(close, index=calendar).where(lambda values: values > 0))
    one_day_return = log_close.diff()
    annualized_volatility = (
        one_day_return.rolling(
            config.volatility_lookback,
            min_periods=config.minimum_volatility_observations,
        ).std(ddof=0)
        * np.sqrt(config.annualization_factor)
    ).to_numpy()

    future_close = sliding_window_view(close[1:], horizon)
    entry_price = open_price[1 : evaluable_count + 1]
    entry_volume = volume[1 : evaluable_count + 1]
    valid_entry = np.isfinite(entry_price) & (entry_price > 0) & np.isfinite(entry_volume) & (
        entry_volume > 0
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        path_return = np.log(future_close / entry_price[:, None])
    finite_path = np.isfinite(path_return)
    future_coverage = finite_path.mean(axis=1)
    terminal_return = path_return[:, -1]
    volatility = annualized_volatility[:evaluable_count]
    horizon_volatility = volatility * np.sqrt(horizon / config.annualization_factor)
    upper = np.clip(
        config.upper_volatility_multiplier * horizon_volatility,
        config.upper_minimum,
        config.upper_maximum,
    )
    lower = np.clip(
        config.lower_volatility_multiplier * horizon_volatility,
        config.lower_minimum,
        config.lower_maximum,
    )

    upper_hit = finite_path & (path_return >= upper[:, None])
    lower_hit = finite_path & (path_return <= -lower[:, None])
    time_to_upper = _first_true(upper_hit)
    time_to_lower = _first_true(lower_hit)
    mfe = _safe_row_max(path_return)
    mae = _safe_row_min(path_return)

    positions = np.arange(1, horizon + 1)[None, :]
    after_upper = positions >= time_to_upper[:, None]
    persistence_denominator = (after_upper & finite_path).sum(axis=1)
    persistence_numerator = (
        after_upper & finite_path & (path_return >= 0.5 * upper[:, None])
    ).sum(axis=1)
    persistence = np.divide(
        persistence_numerator,
        persistence_denominator,
        out=np.full(evaluable_count, np.nan),
        where=persistence_denominator > 0,
    )

    path_with_entry = np.concatenate(
        [np.zeros((evaluable_count, 1)), path_return], axis=1
    )
    adjacent_valid = np.isfinite(path_with_entry[:, 1:]) & np.isfinite(
        path_with_entry[:, :-1]
    )
    path_variation = np.where(
        adjacent_valid,
        np.abs(path_with_entry[:, 1:] - path_with_entry[:, :-1]),
        0.0,
    ).sum(axis=1)
    trend_efficiency = np.divide(
        np.maximum(terminal_return, 0),
        path_variation,
        out=np.full(evaluable_count, np.nan),
        where=path_variation > 0,
    )
    trend_efficiency = np.clip(trend_efficiency, 0, 1)

    with np.errstate(divide="ignore", invalid="ignore"):
        market_return = np.log(
            market_close[horizon:] / market_open[1 : evaluable_count + 1]
        )
    excess_market_return = terminal_return - market_return

    peak_offsets = np.where(np.isfinite(path_return), path_return, -np.inf).argmax(axis=1) + 1
    all_missing_path = ~finite_path.any(axis=1)
    peak_offsets[all_missing_path] = 0

    base_available = (
        feature_ready.reindex(calendar)
        .astype("boolean")
        .fillna(False)
        .to_numpy(dtype=bool)[:evaluable_count]
    )
    volatility_available = np.isfinite(volatility)
    coverage_available = future_coverage >= config.minimum_future_coverage
    terminal_available = np.isfinite(terminal_return)
    market_available = np.isfinite(market_return)

    positive = (
        (time_to_upper < time_to_lower)
        & (time_to_upper <= config.max_time_to_upper)
        & (terminal_return >= config.minimum_terminal_fraction * upper)
        & (persistence >= config.minimum_persistence)
    )
    negative = (time_to_lower < time_to_upper) | (
        (mfe < 0.5 * upper) & (terminal_return <= 0)
    )

    eval_index = calendar[:evaluable_count]
    output.loc[eval_index, "entry_date"] = calendar[1 : evaluable_count + 1].to_numpy()
    output.loc[eval_index, "label_end_date"] = calendar[horizon:].to_numpy()
    peak_dates = np.array(
        [calendar[index + offset] if offset else np.datetime64("NaT") for index, offset in enumerate(peak_offsets)],
        dtype="datetime64[ns]",
    )
    output.loc[eval_index, "peak_date"] = peak_dates
    metric_values = {
        "entry_price": entry_price,
        "upper_barrier": upper,
        "lower_barrier": lower,
        "volatility_at_t": volatility,
        "mfe": mfe,
        "mae": mae,
        "terminal_return": terminal_return,
        "market_return": market_return,
        "excess_market_return": excess_market_return,
        "time_to_upper": np.where(np.isfinite(time_to_upper), time_to_upper, np.nan),
        "time_to_lower": np.where(np.isfinite(time_to_lower), time_to_lower, np.nan),
        "persistence": persistence,
        "trend_efficiency": trend_efficiency,
        "future_coverage": future_coverage,
    }
    for column, values in metric_values.items():
        output.loc[eval_index, column] = values

    gain_quality = np.clip(mfe / upper, 0, 2) / 2.0
    terminal_quality = np.clip(terminal_return / upper, 0, 1)
    drawdown_quality = np.clip(1.0 - np.abs(np.minimum(mae, 0)) / lower, 0, 1)
    market_quality = _sigmoid(excess_market_return / upper)
    candidate_strength = (
        0.30 * gain_quality
        + 0.20 * terminal_quality
        + 0.20 * persistence
        + 0.15 * trend_efficiency
        + 0.10 * drawdown_quality
        + 0.05 * market_quality
    )
    output.loc[eval_index, "candidate_strength"] = np.clip(candidate_strength, 0, 1)

    status = np.full(evaluable_count, "ambiguous", dtype=object)
    candidate_label = np.full(evaluable_count, np.nan)
    status[negative] = "negative"
    candidate_label[negative] = 0
    status[positive] = "candidate_positive"
    candidate_label[positive] = 1

    status[~market_available] = "unavailable_market_path"
    candidate_label[~market_available] = np.nan
    status[~terminal_available] = "censored_missing_terminal"
    candidate_label[~terminal_available] = np.nan
    status[~coverage_available] = "censored_low_future_coverage"
    candidate_label[~coverage_available] = np.nan
    status[~valid_entry] = "unavailable_entry"
    candidate_label[~valid_entry] = np.nan
    status[~volatility_available] = "unavailable_past_volatility"
    candidate_label[~volatility_available] = np.nan
    status[~base_available] = "feature_not_ready"
    candidate_label[~base_available] = np.nan

    output.loc[eval_index, "label_status"] = status
    candidate_series = pd.Series(candidate_label, index=eval_index, dtype="Float64").astype(
        "Int8"
    )
    output.loc[eval_index, "candidate_label"] = candidate_series
    return output.loc[current_observed].reset_index()


def _cluster_events(
    symbol: str,
    labels: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    config: WaveLabelConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    result = labels.copy()
    result["event_id"] = pd.Series(pd.NA, index=result.index, dtype="string")
    result["event_start_date"] = pd.NaT
    result["y_entry"] = pd.Series(pd.NA, index=result.index, dtype="Int8")
    result["y_strength"] = np.nan
    result["sample_weight"] = np.nan

    positive_indices = result.index[result["candidate_label"].eq(1)].tolist()
    clusters: list[list[int]] = []
    for row_index in positive_indices:
        position = int(result.at[row_index, "_calendar_position"])
        if not clusters:
            clusters.append([row_index])
            continue
        previous_cluster = clusters[-1]
        previous_position = int(result.at[previous_cluster[-1], "_calendar_position"])
        start_position = int(result.at[previous_cluster[0], "_calendar_position"])
        same_event = (
            position - previous_position <= config.event_maximum_gap
            or position - start_position <= config.cooldown
        )
        if same_event:
            previous_cluster.append(row_index)
        else:
            clusters.append([row_index])

    events: list[dict[str, Any]] = []
    for event_number, cluster in enumerate(clusters, start=1):
        start_row = cluster[0]
        start_position = int(result.at[start_row, "_calendar_position"])
        last_position = int(result.at[cluster[-1], "_calendar_position"])
        event_id = f"{symbol}_{result.at[start_row, 'date']:%Y%m%d}_{event_number:04d}"
        next_start_position = (
            int(result.at[clusters[event_number][0], "_calendar_position"])
            if event_number < len(clusters)
            else len(calendar)
        )
        event_end_position = min(
            len(calendar) - 1,
            last_position + config.horizon,
            next_start_position - 1,
        )
        overlap_mask = result["_calendar_position"].between(
            start_position, event_end_position
        )
        result.loc[overlap_mask, "event_id"] = event_id
        result.loc[overlap_mask, "event_start_date"] = result.at[start_row, "date"]

        ignition_rows = cluster[: config.ignition_width]
        overlapping_positive_rows = cluster[config.ignition_width :]
        result.loc[ignition_rows, "label_status"] = "positive"
        result.loc[ignition_rows, "y_entry"] = 1
        result.loc[ignition_rows, "y_strength"] = result.loc[
            ignition_rows, "candidate_strength"
        ]
        result.loc[ignition_rows, "sample_weight"] = 1.0 / len(ignition_rows)
        if overlapping_positive_rows:
            result.loc[overlapping_positive_rows, "label_status"] = "overlapping_event"

        protected = set(ignition_rows)
        overlap_rows = result.index[overlap_mask & ~result.index.isin(protected)]
        result.loc[overlap_rows, "y_entry"] = pd.NA
        result.loc[overlap_rows, "y_strength"] = np.nan
        result.loc[overlap_rows, "sample_weight"] = np.nan
        replace_status = result.loc[overlap_rows, "label_status"].isin(
            ["negative", "ambiguous", "candidate_positive"]
        )
        rows_to_replace = overlap_rows[replace_status]
        result.loc[rows_to_replace, "label_status"] = "overlapping_event"

        event_rows = result.loc[cluster]
        strongest_row = event_rows["candidate_strength"].idxmax()
        events.append(
            {
                "event_id": event_id,
                "symbol": symbol,
                "event_start_date": result.at[start_row, "date"],
                "event_entry_date": result.at[start_row, "entry_date"],
                "event_peak_date": result.at[strongest_row, "peak_date"],
                "event_end_date": calendar[event_end_position],
                "candidate_count": len(cluster),
                "positive_label_count": len(ignition_rows),
                "maximum_candidate_strength": event_rows["candidate_strength"].max(),
                "maximum_mfe": event_rows["mfe"].max(),
            }
        )

    clean_negative = result["label_status"].eq("negative") & result["event_id"].isna()
    result.loc[clean_negative, "y_entry"] = 0
    result.loc[clean_negative, "sample_weight"] = 1.0
    result["label_version"] = config.label_version
    event_columns = [
        "event_id",
        "symbol",
        "event_start_date",
        "event_entry_date",
        "event_peak_date",
        "event_end_date",
        "candidate_count",
        "positive_label_count",
        "maximum_candidate_strength",
        "maximum_mfe",
    ]
    return result, pd.DataFrame(events, columns=event_columns)


def label_symbol(
    symbol: str,
    stock_ohlcv: pd.DataFrame,
    vnindex_ohlcv: pd.DataFrame,
    feature_ready: pd.Series,
    config: WaveLabelConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create audited labels and canonical events for a single stock."""
    stock = stock_ohlcv.copy()
    market = vnindex_ohlcv.copy()
    stock["date"] = pd.to_datetime(stock["date"], errors="raise")
    market["date"] = pd.to_datetime(market["date"], errors="raise")
    calendar = pd.DatetimeIndex(market["date"].sort_values().unique(), name="date")
    aligned = stock.set_index("date")[["open", "high", "low", "close", "volume"]]
    aligned = aligned.reindex(calendar)
    market_aligned = market.set_index("date")[["open", "high", "low", "close", "volume"]]
    market_aligned = market_aligned.reindex(calendar)
    ready = feature_ready.copy()
    ready.index = pd.to_datetime(ready.index)
    candidates = _candidate_metrics(aligned, market_aligned, ready, config)
    candidates.insert(0, "symbol", symbol)
    labels, events = _cluster_events(symbol, candidates, calendar, config)
    labels.drop(columns=["_calendar_position", "_current_observed"], inplace=True)
    return labels, events
