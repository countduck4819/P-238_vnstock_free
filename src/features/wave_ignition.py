"""Causal feature engineering for the Wave Ignition model."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from src.features.technical_experimental import ExperimentalFeatureConfig, add_experimental_features

EPSILON = 1e-12


@dataclass(frozen=True)
class FeatureConfig:
    """Versioned parameters controlling feature construction."""

    feature_version: str = "wave_ignition_v1"
    decision_time: str = "after_market_close"
    execution_time: str = "next_session_open"
    industry_level: int = 2
    minimum_sector_members: int = 5
    annualization_factor: int = 252
    windows: tuple[int, ...] = (5, 20, 60, 120)
    minimum_coverage: tuple[tuple[int, float], ...] = (
        (5, 1.0),
        (20, 0.8),
        (60, 0.8),
        (120, 0.8),
    )
    zscore_window: int = 252
    zscore_min_periods: int = 126
    zscore_clip: float = 3.0
    price_adjustment_policy: str = "provider_default_unverified"
    hard_quality_gates: bool = False
    quality_min_coverage_60: float = 0.95
    quality_min_coverage_120: float = 0.92
    quality_max_zero_volume_ratio_60: float = 0.05
    quality_max_stale_sessions: int = 1
    corporate_action_jump: float = 0.30
    corporate_action_cooldown: int = 120
    enable_experimental_features: bool = False
    experimental: ExperimentalFeatureConfig = ExperimentalFeatureConfig()

    @property
    def coverage_by_window(self) -> dict[int, float]:
        return dict(self.minimum_coverage)

    @classmethod
    def from_yaml(cls, path: Path) -> FeatureConfig:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls(
            feature_version=payload["feature_version"],
            decision_time=payload["decision_time"],
            execution_time=payload["execution_time"],
            industry_level=int(payload["industry_level"]),
            minimum_sector_members=int(payload["minimum_sector_members"]),
            annualization_factor=int(payload.get("annualization_factor", 252)),
            windows=tuple(int(value) for value in payload["windows"]),
            minimum_coverage=tuple(
                (int(window), float(value)) for window, value in payload["minimum_coverage"].items()
            ),
            zscore_window=int(payload["normalization"]["zscore_window"]),
            zscore_min_periods=int(payload["normalization"]["zscore_min_periods"]),
            zscore_clip=float(payload["normalization"]["zscore_clip"]),
            price_adjustment_policy=str(payload.get("price_adjustment_policy", "provider_default_unverified")),
            hard_quality_gates=bool(payload.get("quality_gates", {}).get("enabled", False)),
            quality_min_coverage_60=float(payload.get("quality_gates", {}).get("min_coverage_60", 0.95)),
            quality_min_coverage_120=float(payload.get("quality_gates", {}).get("min_coverage_120", 0.92)),
            quality_max_zero_volume_ratio_60=float(payload.get("quality_gates", {}).get("max_zero_volume_ratio_60", 0.05)),
            quality_max_stale_sessions=int(payload.get("quality_gates", {}).get("max_stale_sessions", 1)),
            corporate_action_jump=float(payload.get("quality_gates", {}).get("corporate_action_jump", 0.30)),
            corporate_action_cooldown=int(payload.get("quality_gates", {}).get("corporate_action_cooldown", 120)),
            enable_experimental_features=bool(payload.get("enable_experimental_features", False)),
            experimental=ExperimentalFeatureConfig.from_dict(payload.get("experimental")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_version": self.feature_version,
            "decision_time": self.decision_time,
            "execution_time": self.execution_time,
            "industry_level": self.industry_level,
            "minimum_sector_members": self.minimum_sector_members,
            "annualization_factor": self.annualization_factor,
            "windows": list(self.windows),
            "minimum_coverage": self.coverage_by_window,
            "normalization": {
                "zscore_window": self.zscore_window,
                "zscore_min_periods": self.zscore_min_periods,
                "zscore_clip": self.zscore_clip,
            },
            "price_adjustment_policy": self.price_adjustment_policy,
            "quality_gates": {
                "enabled": self.hard_quality_gates,
                "min_coverage_60": self.quality_min_coverage_60,
                "min_coverage_120": self.quality_min_coverage_120,
                "max_zero_volume_ratio_60": self.quality_max_zero_volume_ratio_60,
                "max_stale_sessions": self.quality_max_stale_sessions,
                "corporate_action_jump": self.corporate_action_jump,
                "corporate_action_cooldown": self.corporate_action_cooldown,
            },
            "enable_experimental_features": self.enable_experimental_features,
            "experimental": self.experimental.to_dict(),
        }


def _minimum_periods(config: FeatureConfig, window: int) -> int:
    ratio = config.coverage_by_window.get(window, 0.8)
    return max(2, int(np.ceil(window * ratio)))


def _safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    return numerator / denominator.replace(0, np.nan)


def _sigmoid(values: pd.Series) -> pd.Series:
    clipped = pd.to_numeric(values, errors="coerce").astype(float).clip(-30, 30)
    return 1.0 / (1.0 + np.exp(-clipped))


def _causal_normalize(series: pd.Series, config: FeatureConfig) -> pd.Series:
    series = pd.to_numeric(series, errors="coerce").astype(float)
    rolling = series.rolling(
        config.zscore_window,
        min_periods=config.zscore_min_periods,
    )
    mean = rolling.mean()
    standard_deviation = rolling.std(ddof=0)
    zscore = _safe_divide(series - mean, standard_deviation)
    zscore = zscore.mask(standard_deviation.eq(0) & mean.notna(), 0.0)
    return np.tanh(zscore.clip(-config.zscore_clip, config.zscore_clip) / 2.0)


def _rolling_trend(
    log_price: pd.Series,
    window: int,
    minimum_periods: int,
    annualization_factor: int,
) -> tuple[pd.Series, pd.Series]:
    """Return annualized OLS slope and R-squared using only the trailing window."""
    x = pd.Series(np.arange(len(log_price), dtype=float), index=log_price.index)
    valid = log_price.notna().astype(float)
    y = log_price.fillna(0.0)
    x_valid = x * valid

    def rolling(value: pd.Series) -> pd.Series:
        return value.rolling(window, min_periods=minimum_periods).sum()

    count = rolling(valid)
    sum_x = rolling(x_valid)
    sum_y = rolling(y)
    sum_xx = rolling(x * x_valid)
    sum_xy = rolling(x * y)
    sum_yy = rolling(y * y)

    covariance_numerator = count * sum_xy - sum_x * sum_y
    variance_x = count * sum_xx - sum_x * sum_x
    variance_y = count * sum_yy - sum_y * sum_y
    slope = _safe_divide(covariance_numerator, variance_x)
    annualized_slope = np.expm1((slope * annualization_factor).clip(-20, 20))
    r_squared = _safe_divide(covariance_numerator.pow(2), variance_x * variance_y).clip(0, 1)
    enough_observations = count >= minimum_periods
    annualized_slope = annualized_slope.where(enough_observations)
    r_squared = r_squared.where(enough_observations)
    return annualized_slope, r_squared


def compute_stock_features(
    aligned_ohlcv: pd.DataFrame,
    market_return: pd.Series | None,
    config: FeatureConfig,
) -> pd.DataFrame:
    """Compute features for one symbol aligned to the VNINDEX trading calendar."""
    frame = aligned_ohlcv.copy()
    observed = frame[["open", "high", "low", "close", "volume"]].notna().all(axis=1)
    log_close = np.log(frame["close"].where(frame["close"] > 0))
    returns = log_close.diff()
    frame["return_1d"] = returns
    # Keep the raw event flag available for point-in-time quality gating.  The
    # feature itself is based on simple price change, while return_1d remains
    # the existing log-return primitive used by the continuation features.
    simple_return = frame["close"].pct_change(fill_method=None)
    frame["corporate_action_jump"] = simple_return.abs().gt(config.corporate_action_jump)
    frame["corporate_action_recent"] = frame["corporate_action_jump"].rolling(
        config.corporate_action_cooldown,
        min_periods=1,
    ).max().fillna(False).astype(bool)

    for window in config.windows:
        minimum_periods = _minimum_periods(config, window)
        coverage = observed.rolling(window, min_periods=1).mean()
        enough_coverage = coverage >= config.coverage_by_window.get(window, 0.8)
        frame[f"coverage_{window}"] = coverage
        frame[f"momentum_{window}"] = (log_close - log_close.shift(window)).where(enough_coverage)

    frame["momentum_acceleration_20"] = frame["momentum_20"] - frame["momentum_20"].shift(20)

    for window in (20, 60):
        minimum_periods = _minimum_periods(config, window)
        rolling_close = frame["close"].rolling(window, min_periods=minimum_periods)
        moving_average = rolling_close.mean()
        frame[f"distance_ma{window}"] = _safe_divide(frame["close"], moving_average) - 1.0
        frame[f"price_cv_{window}"] = _safe_divide(rolling_close.std(ddof=0), moving_average)
        frame[f"tightness_{window}"] = _safe_divide(rolling_close.max() - rolling_close.min(), moving_average)
        slope, r_squared = _rolling_trend(
            log_close,
            window,
            minimum_periods,
            config.annualization_factor,
        )
        frame[f"trend_slope_{window}"] = slope
        frame[f"trend_r2_{window}"] = r_squared

    for window in (10, 20, 60):
        minimum_periods = max(2, int(np.ceil(window * 0.8)))
        frame[f"volatility_{window}"] = returns.rolling(window, min_periods=minimum_periods).std(ddof=0) * np.sqrt(
            config.annualization_factor
        )
    negative_squared_return = returns.where(returns < 0, 0.0).pow(2)
    negative_squared_return = negative_squared_return.where(returns.notna())
    frame["downside_volatility_20"] = np.sqrt(
        negative_squared_return.rolling(20, min_periods=16).mean() * config.annualization_factor
    )
    frame["volatility_ratio_10_60"] = _safe_divide(frame["volatility_10"], frame["volatility_60"])
    frame["contraction_10_60"] = 1.0 - frame["volatility_ratio_10_60"]

    previous_close = frame["close"].shift(1)
    true_range = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1, skipna=False)
    atr_20 = true_range.rolling(20, min_periods=16).mean()
    frame["natr_20"] = _safe_divide(atr_20, frame["close"])

    for window in (20, 60):
        previous_peak = (
            frame["close"]
            .shift(1)
            .rolling(
                window,
                min_periods=_minimum_periods(config, window),
            )
            .max()
        )
        frame[f"breakout_distance_{window}"] = _safe_divide(frame["close"], previous_peak) - 1.0
        frame[f"breakout_atr_{window}"] = _safe_divide(frame["close"] - previous_peak, atr_20)
        frame[f"is_breakout_{window}"] = frame["close"].gt(previous_peak).where(previous_peak.notna()).astype("Float64")

    log_volume = np.log1p(frame["volume"])
    prior_volume_median = frame["volume"].shift(1).rolling(20, min_periods=16).median()
    frame["volume_ratio_20"] = _safe_divide(frame["volume"], prior_volume_median)
    rolling_log_volume = log_volume.rolling(20, min_periods=16)
    frame["volume_zscore_20"] = _safe_divide(
        log_volume - rolling_log_volume.mean(),
        rolling_log_volume.std(ddof=0),
    )
    turnover = frame["close"] * frame["volume"]
    frame["log_turnover"] = np.log1p(turnover)
    frame["log_median_turnover_20"] = np.log1p(turnover.rolling(20, min_periods=16).median())
    frame["log_median_turnover_60"] = np.log1p(turnover.rolling(60, min_periods=48).median())
    frame["zero_volume_ratio_20"] = frame["volume"].eq(0).where(observed).rolling(20, min_periods=16).mean()
    frame["zero_volume_ratio_60"] = frame["volume"].eq(0).where(observed).rolling(60, min_periods=48).mean()

    positions = pd.Series(np.arange(len(frame), dtype=float), index=frame.index)
    observed_positions = positions.where(observed)
    frame["stale_sessions"] = (observed_positions - observed_positions.ffill().shift(1) - 1).where(observed)

    if market_return is not None:
        market_return = market_return.reindex(frame.index)
        covariance = returns.rolling(60, min_periods=48).cov(market_return)
        market_variance = market_return.rolling(60, min_periods=48).var(ddof=0)
        frame["beta_market_60"] = _safe_divide(covariance, market_variance)
        abnormal_return = returns - frame["beta_market_60"] * market_return
        frame["residual_momentum_20"] = abnormal_return.rolling(20, min_periods=16).sum()

    if config.enable_experimental_features:
        frame = add_experimental_features(frame, config.experimental)

    return frame.loc[observed].copy()


def compute_market_features(
    vnindex: pd.DataFrame,
    stock_features: pd.DataFrame,
    universe_size: int,
    config: FeatureConfig,
) -> pd.DataFrame:
    indexed = vnindex.set_index("date").sort_index()
    primitive = compute_stock_features(indexed, None, config)
    market = pd.DataFrame(index=indexed.index)
    market["market_return_1d"] = primitive["return_1d"]
    for window in (5, 20, 60):
        market[f"market_momentum_{window}"] = primitive[f"momentum_{window}"]
    for window in (20, 60):
        market[f"market_distance_ma{window}"] = primitive[f"distance_ma{window}"]
        market[f"market_volatility_{window}"] = primitive[f"volatility_{window}"]

    breadth_source = stock_features.copy()
    breadth_source["_up"] = breadth_source["return_1d"].gt(0).where(breadth_source["return_1d"].notna())
    breadth_source["_above_ma20"] = breadth_source["distance_ma20"].gt(0).where(breadth_source["distance_ma20"].notna())
    daily = breadth_source.groupby("date", sort=True).agg(
        market_active_symbols=("symbol", "nunique"),
        market_breadth_up=("_up", "mean"),
        market_breadth_ma20=("_above_ma20", "mean"),
        market_return_dispersion=("return_1d", "std"),
    )
    market = market.join(daily)
    market["market_advance_decline"] = 2.0 * market["market_breadth_up"] - 1.0
    market["market_coverage"] = market["market_active_symbols"] / universe_size

    components = {
        "market_momentum_20": 0.30,
        "market_momentum_60": 0.20,
        "market_breadth_ma20": 0.20,
        "market_advance_decline": 0.15,
        "market_volatility_20": -0.15,
    }
    normalized = {name: _causal_normalize(market[name], config) for name in components}
    raw_score = sum(normalized[name] * weight for name, weight in components.items())
    market["market_regime_score"] = 100.0 * _sigmoid(raw_score)
    return market.reset_index()


def compute_sector_features(
    stock_features: pd.DataFrame,
    market_features: pd.DataFrame,
    sector_universe_sizes: pd.Series,
    calendar: pd.DatetimeIndex,
    sector_column: str,
    config: FeatureConfig,
) -> pd.DataFrame:
    source = stock_features.copy()
    source["_up"] = source["return_1d"].gt(0).where(source["return_1d"].notna())
    source["_above_ma20"] = source["distance_ma20"].gt(0).where(source["distance_ma20"].notna())
    source["_positive_flow"] = (source["return_1d"].gt(0) & source["volume_zscore_20"].gt(1)).where(
        source[["return_1d", "volume_zscore_20"]].notna().all(axis=1)
    )

    grouped = source.groupby([sector_column, "date"], sort=True).agg(
        sector_return_1d=("return_1d", "mean"),
        sector_active_symbols=("symbol", "nunique"),
        sector_breadth_up=("_up", "mean"),
        sector_breadth_ma20=("_above_ma20", "mean"),
        sector_positive_flow_breadth=("_positive_flow", "mean"),
        sector_return_dispersion=("return_1d", "std"),
    )

    sectors: list[pd.DataFrame] = []
    for sector_code, sector_frame in grouped.groupby(level=0, sort=True):
        aligned = sector_frame.droplevel(0).reindex(calendar)
        aligned.index.name = "date"
        for window in (5, 20, 60):
            aligned[f"sector_momentum_{window}"] = (
                aligned["sector_return_1d"].rolling(window, min_periods=_minimum_periods(config, window)).sum()
            )
        aligned[sector_column] = sector_code
        sectors.append(aligned.reset_index())
    result = pd.concat(sectors, ignore_index=True)
    result["sector_coverage"] = result["sector_active_symbols"] / result[sector_column].map(sector_universe_sizes)
    result = result.merge(
        market_features[["date", "market_momentum_20", "market_momentum_60"]],
        on="date",
        how="left",
        validate="many_to_one",
    )
    for window in (20, 60):
        result[f"sector_relative_market_{window}"] = (
            result[f"sector_momentum_{window}"] - result[f"market_momentum_{window}"]
        )
        result[f"sector_rank_{window}"] = result.groupby("date", sort=False)[f"sector_momentum_{window}"].rank(pct=True)

    valid_sector = result["sector_active_symbols"] >= config.minimum_sector_members
    sector_feature_columns = [
        column for column in result.columns if column.startswith("sector_") and column not in {"sector_active_symbols"}
    ]
    result.loc[~valid_sector, sector_feature_columns] = np.nan

    component_weights = {
        "sector_relative_market_20": 0.30,
        "sector_relative_market_60": 0.20,
        "sector_breadth_ma20": 0.20,
        "sector_positive_flow_breadth": 0.15,
        "sector_rank_20": 0.15,
    }
    normalized_components: list[pd.Series] = []
    for name, weight in component_weights.items():
        normalized = result.groupby(sector_column, sort=False)[name].transform(
            lambda values: _causal_normalize(values, config)
        )
        normalized_components.append(normalized * weight)
    raw_score = sum(normalized_components)
    result["sector_strength_score"] = 100.0 * _sigmoid(raw_score)
    return result.loc[result["sector_active_symbols"].notna()].reset_index(drop=True)


def add_relative_and_composite_features(
    stock_features: pd.DataFrame,
    market_features: pd.DataFrame,
    sector_features: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    sector_column: str,
    config: FeatureConfig,
) -> pd.DataFrame:
    market_columns = [column for column in market_features.columns if column == "date" or column.startswith("market_")]
    result = stock_features.merge(market_features[market_columns], on="date", how="left", validate="many_to_one")
    sector_columns = [
        column
        for column in sector_features.columns
        if column in {"date", sector_column} or column.startswith("sector_")
    ]
    result = result.merge(
        sector_features[sector_columns],
        on=["date", sector_column],
        how="left",
        validate="many_to_one",
    )

    for window in (20, 60):
        result[f"relative_market_{window}"] = result[f"momentum_{window}"] - result[f"market_momentum_{window}"]
        result[f"relative_sector_{window}"] = result[f"momentum_{window}"] - result[f"sector_momentum_{window}"]

    rank_sources = {
        "sector_rank_relative_strength_20": "relative_sector_20",
        "sector_rank_relative_strength_60": "relative_sector_60",
        "sector_rank_volume_zscore": "volume_zscore_20",
        "sector_rank_liquidity": "log_median_turnover_20",
        "sector_rank_trend_quality": "trend_r2_60",
    }
    for output, source in rank_sources.items():
        result[output] = result.groupby(["date", sector_column], sort=False)[source].rank(pct=True)

    leader_matrix = result.pivot(index="date", columns="symbol", values="sector_rank_relative_strength_20")
    leader_matrix = leader_matrix.reindex(calendar)
    leader_flag = leader_matrix.gt(0.8).where(leader_matrix.notna())
    consistency = leader_flag.rolling(20, min_periods=16).mean()
    consistency_long = consistency.stack(future_stack=True).rename("leader_consistency_20").reset_index()
    result = result.merge(consistency_long, on=["date", "symbol"], how="left")

    leader_columns = [*rank_sources, "leader_consistency_20"]
    leader_weights = np.array([0.25, 0.15, 0.15, 0.10, 0.15, 0.20])
    weighted_leader = result[leader_columns].mul(leader_weights, axis=1)
    result["leader_score"] = 100.0 * weighted_leader.sum(axis=1, min_count=len(leader_columns))

    normalization_sources = {
        "_n_momentum_acceleration": "momentum_acceleration_20",
        "_n_contraction": "contraction_10_60",
        "_n_breakout": "breakout_atr_20",
        "_n_volume": "volume_zscore_20",
        "_n_relative_sector": "relative_sector_20",
    }
    for output, source in normalization_sources.items():
        result[output] = result.groupby("symbol", sort=False)[source].transform(
            lambda values: _causal_normalize(values, config)
        )
    confirmation = result["_n_breakout"] * result["_n_volume"].clip(lower=0)
    ignition_raw = (
        0.15 * result["_n_momentum_acceleration"]
        + 0.15 * result["_n_contraction"]
        + 0.20 * result["_n_breakout"]
        + 0.15 * result["_n_volume"]
        + 0.15 * result["_n_relative_sector"]
        + 0.20 * confirmation
    )
    result["stock_ignition_score"] = 100.0 * _sigmoid(ignition_raw)
    result.drop(columns=list(normalization_sources), inplace=True)

    result["quality_score"] = 100.0 * (
        0.50 * result["coverage_60"] + 0.30 * result["coverage_120"] + 0.20 * (1.0 - result["zero_volume_ratio_60"])
    ).clip(0, 1)
    combined = (
        0.20 * result["market_regime_score"]
        + 0.25 * result["sector_strength_score"]
        + 0.35 * result["stock_ignition_score"]
        + 0.20 * result["leader_score"]
    )
    result["wave_feature_score"] = combined * result["quality_score"] / 100.0
    result["feature_ready"] = result["quality_score"].ge(70) & result[
        [
            "market_regime_score",
            "sector_strength_score",
            "stock_ignition_score",
            "leader_score",
        ]
    ].notna().all(axis=1)
    if config.hard_quality_gates:
        result["feature_ready"] &= (
            result["coverage_60"].ge(config.quality_min_coverage_60)
            & result["coverage_120"].ge(config.quality_min_coverage_120)
            & result["zero_volume_ratio_60"].le(config.quality_max_zero_volume_ratio_60)
            & result["stale_sessions"].fillna(np.inf).le(config.quality_max_stale_sessions)
            & ~result["corporate_action_recent"].fillna(True)
        )
    result["feature_version"] = config.feature_version
    return result.sort_values(["date", "symbol"], kind="stable").reset_index(drop=True)


def build_feature_tables(
    stock_ohlcv: pd.DataFrame,
    vnindex_ohlcv: pd.DataFrame,
    industry_map: pd.DataFrame,
    config: FeatureConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build stock, market and sector feature tables from cleaned inputs."""
    stock = stock_ohlcv.copy()
    vnindex = vnindex_ohlcv.copy()
    stock["date"] = pd.to_datetime(stock["date"], errors="raise")
    vnindex["date"] = pd.to_datetime(vnindex["date"], errors="raise")
    calendar = pd.DatetimeIndex(vnindex["date"].sort_values().unique(), name="date")
    market_return = np.log(vnindex.set_index("date")["close"].sort_index()).diff().reindex(calendar)

    level = config.industry_level
    sector_code = f"icb_level_{level}_code"
    sector_name = f"icb_level_{level}_name"
    mapping = industry_map[["symbol", sector_code, sector_name]].drop_duplicates("symbol")
    stock = stock.merge(mapping, on="symbol", how="left", validate="many_to_one")
    if stock[sector_code].isna().any():
        missing = sorted(stock.loc[stock[sector_code].isna(), "symbol"].unique())
        raise ValueError(f"Missing ICB level {level} mapping for: {missing[:10]}")

    stock_frames: list[pd.DataFrame] = []
    for symbol, source in stock.groupby("symbol", sort=True):
        metadata = source[[sector_code, sector_name]].iloc[0]
        aligned = source.set_index("date")[["open", "high", "low", "close", "volume"]]
        aligned = aligned.reindex(calendar)
        features = compute_stock_features(aligned, market_return, config)
        features.insert(0, "date", features.index)
        features.insert(0, "symbol", symbol)
        features[sector_code] = metadata[sector_code]
        features[sector_name] = metadata[sector_name]
        stock_frames.append(features.reset_index(drop=True))
    primitive_stock = pd.concat(stock_frames, ignore_index=True)

    market_features = compute_market_features(
        vnindex,
        primitive_stock,
        universe_size=stock["symbol"].nunique(),
        config=config,
    )
    sector_sizes = mapping.groupby(sector_code)["symbol"].nunique()
    sector_features = compute_sector_features(
        primitive_stock,
        market_features,
        sector_sizes,
        calendar,
        sector_code,
        config,
    )
    final_stock = add_relative_and_composite_features(
        primitive_stock,
        market_features,
        sector_features,
        calendar,
        sector_code,
        config,
    )
    return final_stock, market_features, sector_features
