"""Early major-uptrend discovery pipeline for Vietnamese equities.

Goal
----
Rank the current Vietnamese equity universe by the probability that a stock is
still in an *early state* before a confirmed strong future wave. The label has
no fixed forecast horizon: it follows the observed future path until either a
confirmed major wave or a confirmed structural breakdown resolves the current
episode. Unresolved paths at the snapshot end are right-censored, never forced
to class 0.

A positive is not a simple ``future return >= 50%`` rule.  The future price must
reach the return threshold on a date that also satisfies persistent 60-session
trend-quality conditions.  A point-in-time pre-wave gate prevents already
overextended rows from becoming positives. Very late positives remain positive
but receive a smooth lead-time relevance discount, so an accidental wave years
later cannot dominate genuine precursor states. The gate/discount are historical
training controls only; live stocks are never hard-removed and still receive
separate wave-probability and entry-quality scores.

Leakage control
---------------
* Features use only information available at or before date t.
* Stock quality filters are point-in-time rolling filters; a ticker is never
  removed from historical training because of quality observed years later.
* Feature screening / clipping / imputation are fitted on TRAIN only.
* Train/calibration/test splits are by market date, and a training/calibration
  row is allowed only when label_end_time is strictly before the next split.
* Latest rows are inference only.

Paper-derived technical layer
-----------------------------
The 10 indicator families from Nabipour et al. (IEEE Access, 2020) are included
in scale-aware form suitable for a multi-stock panel, plus their +1/-1 trend
signals: SMA, WMA, MOM, STCK, STCD, RSI, MACD signal (SIG), Williams %R (LWR),
ADO, and CCI.  The paper's signal rules are preserved where applicable.

Outputs
-------
* per-model calibration and final-holdout metrics
* individual XGBoost / LightGBM / CatBoost probabilities
* learned weighted-ensemble probability
* top 50 latest candidates with probabilities from every model
* a separate, interpretable entry-quality/overextension layer
* feature quality / selected-feature / data-quality reports
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import warnings
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import joblib
import numpy as np
import optuna
import pandas as pd
from catboost import CatBoostClassifier
from lightgbm import LGBMClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    log_loss,
    matthews_corrcoef,
    precision_score,
    recall_score,
    roc_auc_score,
)
from xgboost import XGBClassifier

from check_prediction_correlation import (
    prediction_correlation_report,
    print_prediction_correlation,
)
from portfolio_ranking_v6 import (
    PortfolioRankingConfig,
    add_portfolio_quality_scores,
    compare_holdout_rankings,
    ranking_profile,
    select_diversified_top_k,
)

EPS = 1e-8
MODEL_NAMES = ("xgb", "lgb", "cat")
CANONICAL_MODEL_NAMES = ("xgb", "lgb", "cat")


@dataclass(frozen=True)
class Config:
    data_dir: str = "data_vnstock"
    market_path: str = "market/VNINDEX.csv"
    industry_path: str = "data_vnstock/industry_map.csv"
    market_cap_path: str = "data_vnstock/symbols.csv"
    models_dir: str = "models_wave_v6"
    reports_dir: str = "reports_wave_v6"
    compute_device: str = "cpu"

    # Time-agnostic first resolved episode: confirmed wave versus confirmed
    # structural breakdown. 126/252 below are backtest horizons, not label limits.
    strong_wave_return: float = 0.50
    round_trip_cost: float = 0.005
    structural_failure_drawdown: float = -0.35
    failure_max_return_60: float = -0.15
    failure_max_slope_60: float = -0.0008
    failure_min_r2_60: float = 0.20
    failure_min_observed_ratio_60: float = 0.90
    lead_time_half_life_sessions: int = 504
    min_late_positive_relevance: float = 0.15
    # A price touch alone is not a major wave.  The confirmation date must also
    # exhibit a persistent, reasonably smooth 60-session uptrend.
    confirmation_min_return_60: float = 0.20
    confirmation_min_slope_60: float = 0.0010
    confirmation_min_r2_60: float = 0.25
    confirmation_max_drawdown_60: float = -0.18
    confirmation_min_observed_ratio_60: float = 0.95

    # Point-in-time historical target gate: a future wave is positive only when
    # the stock was not already far into that wave at feature date t. Thresholds
    # are intentionally broad; entry_quality remains the finer live timing layer.
    early_max_return_60: float = 0.45
    early_max_return_120: float = 0.80
    early_max_price_to_ma50: float = 0.35
    early_max_price_to_ma200: float = 0.70
    early_max_atr_extension_20: float = 6.0
    early_max_breakout_prior_high_252: float = 0.20

    # Point-in-time quality / junk-stock rejection.
    min_history_sessions: int = 260
    min_observed_ratio_60: float = 0.95
    min_observed_ratio_120: float = 0.92
    max_zero_volume_ratio_60: float = 0.05
    # vnstock equity prices in this snapshot are quoted in thousand VND.  This
    # multiplier is used ONLY for traded-value liquidity, never price returns.
    price_value_multiplier: float = 1_000.0
    corporate_action_jump: float = 0.30
    corporate_action_cooldown: int = 60
    max_volume_ratio_feature: float = 20.0
    max_raw_volume_ratio: float = 50.0
    abnormal_volume_cooldown: int = 5
    min_row_feature_coverage: float = 0.90
    # Weekly point-in-time snapshots reduce five near-duplicate daily labels per
    # ticker to one coherent cross-section while live inference remains daily.
    supervised_sample_stride: int = 5
    supervised_sample_weekday: int | None = None
    supervised_sample_anchor_date: str | None = None

    # Train-only feature cleanup.
    max_feature_missing_rate: float = 0.08
    min_feature_unique_values: int = 8
    max_pairwise_abs_spearman: float = 0.95
    clip_quantile_low: float = 0.005
    clip_quantile_high: float = 0.995
    feature_screen_sample: int = 150_000

    # Date-level evaluation. The maturity buffer is solely for 1-year Top-50
    # realised-outcome diagnostics; it is not a label horizon.
    calibration_sessions: int = 252
    test_sessions: int = 252
    evaluation_maturity_sessions: int = 252
    cv_splits: int = 3
    min_cv_train_sessions: int = 504
    min_cv_validation_sessions: int = 63
    ablation_calibration_sessions: int = 63
    optuna_trials: int = 15
    min_selected_features: int = 6

    # Ensemble admission is decided on calibration only.
    min_model_roc_auc: float = 0.52
    min_model_pr_lift: float = 1.05
    min_model_top_k_lift: float = 1.05
    max_ensemble_weight: float = 1.00
    min_ensemble_score_gain: float = 0.005

    # Snapshot integrity.
    freshness_days: int = 10
    min_fresh_symbols: int = 100
    min_model_symbols: int = 100
    min_latest_symbols: int = 100
    min_snapshot_coverage: float = 0.90
    min_industry_coverage: float = 0.90

    top_k_per_day: int = 50
    latest_top_n: int = 50
    backtest_rebalance_sessions: int = 21
    random_seed: int = 42


PAPER_CONTINUOUS = [
    "sma10_gap",
    "wma14_gap",
    "mom10_pct",
    "stoch_k10",
    "stoch_d10",
    "rsi10",
    "macd_signal_norm",
    "williams_r10",
    "ado",
    "cci10",
]

PAPER_BINARY = [
    "sig_sma",
    "sig_wma",
    "sig_mom",
    "sig_stoch_k",
    "sig_stoch_d",
    "sig_rsi",
    "sig_macd",
    "sig_lwr",
    "sig_ado",
    "sig_cci",
]

PRICE_TREND_FEATURES = [
    "ret_60",
    "price_to_ma50",
    "price_to_ma200",
    "ma50_to_ma200",
    "slope_60",
    "trend_r2_60",
]

VOLUME_REGIME_FEATURES = [
    "volume_ratio_20",
    "volume_ratio_short_long",
    "volume_persistence_20",
    "up_down_volume_ratio_60",
    "volume_trend_60",
    "value_regime_20_120",
    "liquidity_percentile",
]

RELATIVE_STRENGTH_FEATURES = [
    "stock_rs_market_20",
    "stock_rs_market_60",
    "rs_improvement_20_vs_60",
    "rs_rank_market_60",
    "rs_rank_change_20",
    "rs_rank_sector_60",
    "sector_rs_60",
]

ACCUMULATION_BASE_FEATURES = [
    "base_range_60",
    "base_range_120",
    "base_stability_120",
    "volatility_contraction_20_120",
    "atr_contraction_14_60",
    "range_contraction_20_120",
    "distance_from_high_252",
    "distance_from_prior_high_252",
]

MARKET_SECTOR_CONTEXT_FEATURES = [
    "market_ret_60",
    "market_price_to_ma200",
    "market_breadth_ma50",
    "sector_ret_60",
    "sector_breadth_ma50",
    "sector_rank_60",
]

CANDIDATE_FEATURES = list(dict.fromkeys(
    PAPER_CONTINUOUS + PAPER_BINARY + PRICE_TREND_FEATURES + VOLUME_REGIME_FEATURES +
    RELATIVE_STRENGTH_FEATURES + ACCUMULATION_BASE_FEATURES + MARKET_SECTOR_CONTEXT_FEATURES
))

FEATURE_EXPERIMENTS = {
    "A_paper_continuous": PAPER_CONTINUOUS,
    "B_paper_binary": PAPER_BINARY,
    "C_paper_all": PAPER_CONTINUOUS + PAPER_BINARY,
    "D_price_trend_volume": PRICE_TREND_FEATURES + VOLUME_REGIME_FEATURES,
    "E_plus_relative_strength": (
        PRICE_TREND_FEATURES + VOLUME_REGIME_FEATURES + RELATIVE_STRENGTH_FEATURES
    ),
    "F_plus_accumulation_base": (
        PRICE_TREND_FEATURES + VOLUME_REGIME_FEATURES + RELATIVE_STRENGTH_FEATURES +
        ACCUMULATION_BASE_FEATURES
    ),
    "G_plus_market_sector_context": (
        PRICE_TREND_FEATURES + VOLUME_REGIME_FEATURES + RELATIVE_STRENGTH_FEATURES +
        ACCUMULATION_BASE_FEATURES + MARKET_SECTOR_CONTEXT_FEATURES
    ),
    "H_all_plus_paper": CANDIDATE_FEATURES,
}


# ---------------------------------------------------------------------------
# I/O and data sanity
# ---------------------------------------------------------------------------

def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = (
        out.columns.astype(str)
        .str.replace(r"[^\x00-\x7F]+", "", regex=True)
        .str.strip()
        .str.lower()
    )
    aliases = {
        "date": "time", "datetime": "time", "symbol": "ticker", "code": "ticker",
        "industry_name": "industry", "icb_name": "industry",
        "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume",
    }
    return out.rename(columns={k: v for k, v in aliases.items() if k in out.columns})


def _safe_numeric_mean(values: pd.Series) -> float:
    """Return a float mean, including ``nan`` for an all-missing nullable series."""
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    return float(numeric.mean()) if not numeric.empty else float("nan")


def _safe_numeric_median(values: pd.Series) -> float:
    """Return a float median, including ``nan`` for an all-missing series."""
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    return float(numeric.median()) if not numeric.empty else float("nan")


def load_ohlcv(path: Path) -> pd.DataFrame:
    df = _normalise_columns(pd.read_csv(path))
    required = ["time", "open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"{path.name}: missing columns {missing}")
    df = df[required].copy()
    df["time"] = pd.to_datetime(df["time"], errors="coerce").dt.normalize()
    for col in required[1:]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = (
        df.dropna(subset=["time"])
        .drop_duplicates("time", keep="last")
        .sort_values("time")
        .reset_index(drop=True)
    )
    valid_price = (
        (df["open"] > 0) & (df["high"] > 0) & (df["low"] > 0) & (df["close"] > 0) &
        (df["high"] >= df[["open", "close", "low"]].max(axis=1)) &
        (df["low"] <= df[["open", "close", "high"]].min(axis=1))
    )
    df.loc[~valid_price, ["open", "high", "low", "close"]] = np.nan
    df.loc[(df["volume"] < 0) | ~np.isfinite(df["volume"]), "volume"] = np.nan
    return df


def align_stock_to_market_calendar(stock: pd.DataFrame, market_calendar: pd.Series) -> pd.DataFrame:
    """Align to market sessions WITHOUT forward-filling price candles.

    A suspended/missing day remains NaN in OHLC and volume=0. This intentionally
    makes rolling technical features unavailable after repeated gaps, which is a
    desirable point-in-time quality filter for the user's use case.
    """
    if stock.empty:
        return stock
    calendar = pd.DatetimeIndex(pd.to_datetime(market_calendar).dropna().unique()).sort_values()
    calendar = calendar[(calendar >= stock["time"].min()) & (calendar <= stock["time"].max())]
    aligned = stock.set_index("time").reindex(calendar)
    aligned.index.name = "time"
    aligned["observed"] = aligned[["open", "high", "low", "close"]].notna().all(axis=1)
    aligned["volume"] = aligned["volume"].where(aligned["observed"], 0.0).fillna(0.0)
    return aligned.reset_index()


def load_industry_map(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    df = _normalise_columns(pd.read_csv(path))
    ticker_col = next((c for c in ("ticker", "symbol") if c in df.columns), None)
    industry_col = next(
        (c for c in ("industry", "industry_name", "icb_name2", "icb_name3", "sector") if c in df.columns),
        None,
    )
    if ticker_col is None or industry_col is None:
        return {}
    clean = df[[ticker_col, industry_col]].dropna().drop_duplicates(ticker_col, keep="last")
    return dict(zip(clean[ticker_col].astype(str).str.upper(), clean[industry_col].astype(str)))


def load_market_cap_map(path: Path) -> dict[str, float]:
    """Load an optional current market-cap snapshot for latest ranking only.

    Historical evaluation deliberately does not reuse a current market cap,
    because doing so would introduce look-ahead bias. Missing or weak coverage
    is handled transparently by the ranking module's liquidity proxy.
    """
    if not path.exists():
        return {}
    frame = _normalise_columns(pd.read_csv(path))
    ticker_col = next((c for c in ("ticker", "symbol") if c in frame), None)
    cap_col = next(
        (c for c in ("market_cap", "marketcap", "market_capitalization", "capitalization") if c in frame),
        None,
    )
    if ticker_col is None or cap_col is None:
        return {}
    clean = frame[[ticker_col, cap_col]].copy()
    clean[ticker_col] = clean[ticker_col].astype(str).str.strip().str.upper()
    clean[cap_col] = pd.to_numeric(clean[cap_col], errors="coerce")
    clean = clean.loc[clean[cap_col].gt(0)].drop_duplicates(ticker_col, keep="last")
    return dict(zip(clean[ticker_col], clean[cap_col].astype(float)))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def cache_freshness(files: Iterable[Path], cfg: Config) -> dict[str, Any]:
    endings: dict[str, pd.Timestamp] = {}
    for path in files:
        try:
            tail = pd.read_csv(path, usecols=["time"]).tail(1)
            if not tail.empty:
                endings[path.stem.upper()] = pd.to_datetime(tail.iloc[0, 0]).normalize()
        except Exception:
            continue
    if not endings:
        raise RuntimeError("No readable stock CSV files were found")
    newest = max(endings.values())
    cutoff = newest - pd.Timedelta(days=cfg.freshness_days)
    fresh = sorted(symbol for symbol, end in endings.items() if end >= cutoff)
    return {
        "newest_date": str(newest.date()),
        "freshness_cutoff": str(cutoff.date()),
        "total_symbols": len(endings),
        "fresh_symbols": len(fresh),
        "fresh_symbol_sample": fresh[:25],
    }


# ---------------------------------------------------------------------------
# Backward-looking feature engineering
# ---------------------------------------------------------------------------

def _rolling_slope_pct(values: np.ndarray) -> float:
    if np.isnan(values).any() or values[-1] <= 0:
        return np.nan
    x = np.arange(values.size, dtype=float)
    return float(np.polyfit(x, values, 1)[0] / values[-1])


def _rolling_r2(values: np.ndarray) -> float:
    if np.isnan(values).any() or np.all(values == values[0]):
        return np.nan
    x = np.arange(values.size, dtype=float)
    corr = np.corrcoef(x, values)[0, 1]
    return float(corr * corr)


def _rolling_max_drawdown(values: np.ndarray) -> float:
    if np.isnan(values).any() or np.any(values <= 0):
        return np.nan
    peaks = np.maximum.accumulate(values)
    return float(np.min(values / peaks - 1.0))


def _rolling_trend_series(
    values: pd.Series,
    window: int,
) -> tuple[pd.Series, pd.Series]:
    """Vectorised rolling slope/last-price and linear-trend R2."""
    array = values.to_numpy(float)
    slope_result = np.full(len(array), np.nan, dtype=float)
    r2_result = np.full(len(array), np.nan, dtype=float)
    if len(array) < window:
        return pd.Series(slope_result, index=values.index), pd.Series(r2_result, index=values.index)
    windows = np.lib.stride_tricks.sliding_window_view(array, window)
    valid = np.isfinite(windows).all(axis=1) & (windows[:, -1] > 0)
    x = np.arange(window, dtype=float)
    x_centered = x - x.mean()
    x_ss = float(np.dot(x_centered, x_centered))
    safe_windows = np.where(np.isfinite(windows), windows, 0.0)
    centered_y = safe_windows - safe_windows.mean(axis=1, keepdims=True)
    covariance_numerator = centered_y @ x_centered
    slope = covariance_numerator / x_ss
    y_ss = np.sum(centered_y * centered_y, axis=1)
    r2 = np.divide(
        covariance_numerator * covariance_numerator,
        x_ss * y_ss,
        out=np.full_like(covariance_numerator, np.nan),
        where=y_ss > EPS,
    )
    positions = np.arange(window - 1, len(array))
    slope_result[positions[valid]] = slope[valid] / windows[valid, -1]
    r2_result[positions[valid]] = r2[valid]
    return pd.Series(slope_result, index=values.index), pd.Series(r2_result, index=values.index)


def _rolling_max_drawdown_series(values: pd.Series, window: int) -> pd.Series:
    """Vectorised max drawdown inside each fixed rolling window."""
    array = values.to_numpy(float)
    result = np.full(len(array), np.nan, dtype=float)
    if len(array) < window:
        return pd.Series(result, index=values.index)
    windows = np.lib.stride_tricks.sliding_window_view(array, window)
    valid = np.isfinite(windows).all(axis=1) & (windows > 0).all(axis=1)
    safe_windows = np.where(valid[:, None], windows, 1.0)
    peaks = np.maximum.accumulate(safe_windows, axis=1)
    drawdown = np.min(safe_windows / peaks - 1.0, axis=1)
    positions = np.arange(window - 1, len(array))
    result[positions[valid]] = drawdown[valid]
    return pd.Series(result, index=values.index)


def _rsi_sma(close: pd.Series, window: int) -> pd.Series:
    """RSI using rolling mean gains/losses, close to the paper's n-period formula."""
    delta = close.diff()
    up = delta.clip(lower=0).rolling(window, min_periods=window).mean()
    down = (-delta.clip(upper=0)).rolling(window, min_periods=window).mean()
    rs = up / (down + EPS)
    return 100 - 100 / (1 + rs)


def _weighted_moving_average(close: pd.Series, window: int) -> pd.Series:
    weights = np.arange(1, window + 1, dtype=float)
    array = close.to_numpy(float)
    result = np.full(len(array), np.nan, dtype=float)
    if len(array) < window:
        return pd.Series(result, index=close.index)
    windows = np.lib.stride_tricks.sliding_window_view(array, window)
    valid = np.isfinite(windows).all(axis=1)
    weighted = np.where(np.isfinite(windows), windows, 0.0) @ weights / float(weights.sum())
    positions = np.arange(window - 1, len(array))
    result[positions[valid]] = weighted[valid]
    return pd.Series(result, index=close.index)


def _rolling_mean_abs_deviation_series(values: pd.Series, window: int) -> pd.Series:
    array = values.to_numpy(float)
    result = np.full(len(array), np.nan, dtype=float)
    if len(array) < window:
        return pd.Series(result, index=values.index)
    windows = np.lib.stride_tricks.sliding_window_view(array, window)
    valid = np.isfinite(windows).all(axis=1)
    safe_windows = np.where(np.isfinite(windows), windows, 0.0)
    means = safe_windows.mean(axis=1, keepdims=True)
    deviation = np.mean(np.abs(safe_windows - means), axis=1)
    positions = np.arange(window - 1, len(array))
    result[positions[valid]] = deviation[valid]
    return pd.Series(result, index=values.index)


def add_stock_features(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    out = df.copy()
    close = out["close"].astype(float)
    high = out["high"].astype(float)
    low = out["low"].astype(float)
    volume = out["volume"].astype(float).fillna(0.0)
    observed = out["observed"].fillna(False)

    ret_1 = close.pct_change(fill_method=None)
    out["ret_1"] = ret_1
    for window in (5, 20, 60, 120):
        out[f"ret_{window}"] = close.pct_change(window, fill_method=None)

    # Paper-derived continuous indicators.
    sma10 = close.rolling(10, min_periods=10).mean()
    wma14 = _weighted_moving_average(close, 14)
    out["sma10_gap"] = close / (sma10 + EPS) - 1
    out["wma14_gap"] = close / (wma14 + EPS) - 1
    out["mom10_pct"] = close / close.shift(9) - 1

    low10 = low.rolling(10, min_periods=10).min()
    high10 = high.rolling(10, min_periods=10).max()
    stoch_k = 100 * (close - low10) / (high10 - low10 + EPS)
    stoch_d = stoch_k.rolling(10, min_periods=10).mean()
    out["stoch_k10"] = stoch_k
    out["stoch_d10"] = stoch_d
    out["rsi10"] = _rsi_sma(close, 10)

    ema12 = close.ewm(span=12, adjust=False, min_periods=12).mean()
    ema26 = close.ewm(span=26, adjust=False, min_periods=26).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(span=9, adjust=False, min_periods=9).mean()
    out["macd_signal_norm"] = macd_signal / (close + EPS)

    # Paper LWR is 100*(HH-C)/(HH-LL), i.e. positive 0..100 orientation.
    out["williams_r10"] = 100 * (high10 - close) / (high10 - low10 + EPS)
    # Paper ADO formula, not the more common Chaikin A/D line.
    out["ado"] = (high - close) / (high - low + EPS)

    typical = (high + low + close) / 3.0
    typical_mean10 = typical.rolling(10, min_periods=10).mean()
    mean_dev10 = _rolling_mean_abs_deviation_series(typical, 10)
    out["cci10"] = (typical - typical_mean10) / (0.015 * mean_dev10 + EPS)

    # Paper's +1/-1 signal transformation.
    out["sig_sma"] = np.where(
        close.notna() & sma10.notna(), np.where(close >= sma10, 1.0, -1.0), np.nan
    )
    out["sig_wma"] = np.where(
        close.notna() & wma14.notna(), np.where(close >= wma14, 1.0, -1.0), np.nan
    )
    mom = out["mom10_pct"]
    out["sig_mom"] = np.where(mom.notna(), np.where(mom > 0, 1.0, -1.0), np.nan)
    for source, target in (
        ("stoch_k10", "sig_stoch_k"),
        ("stoch_d10", "sig_stoch_d"),
        ("macd_signal_norm", "sig_macd"),
        ("williams_r10", "sig_lwr"),
        ("ado", "sig_ado"),
    ):
        cur, prev = out[source], out[source].shift(1)
        out[target] = np.where(
            cur.notna() & prev.notna(), np.where(cur > prev, 1.0, -1.0), np.nan
        )

    rsi = out["rsi10"]
    rsi_prev = rsi.shift(1)
    rsi_dir = np.where(rsi > rsi_prev, 1.0, -1.0)
    out["sig_rsi"] = np.where(
        rsi.notna() & rsi_prev.notna(),
        np.where(rsi > 70, -1.0, np.where(rsi < 30, 1.0, rsi_dir)),
        np.nan,
    )
    cci = out["cci10"]
    cci_prev = cci.shift(1)
    cci_dir = np.where(cci > cci_prev, 1.0, -1.0)
    out["sig_cci"] = np.where(
        cci.notna() & cci_prev.notna(),
        np.where(cci > 200, -1.0, np.where(cci < -200, 1.0, cci_dir)),
        np.nan,
    )

    # Additional compact context features for a market-wide model.
    ma20 = close.rolling(20, min_periods=20).mean()
    ma50 = close.rolling(50, min_periods=50).mean()
    ma200 = close.rolling(200, min_periods=200).mean()
    out["price_to_ma20"] = close / (ma20 + EPS) - 1
    out["price_to_ma50"] = close / (ma50 + EPS) - 1
    out["price_to_ma200"] = close / (ma200 + EPS) - 1
    out["ma50_to_ma200"] = ma50 / (ma200 + EPS) - 1
    out["above_ma50"] = (close > ma50).where(ma50.notna()).astype(float)
    out["slope_20"], _ = _rolling_trend_series(close, 20)
    out["slope_60"], out["trend_r2_60"] = _rolling_trend_series(close, 60)
    out["volatility_20"] = ret_1.rolling(20, min_periods=20).std()
    out["volatility_60"] = ret_1.rolling(60, min_periods=60).std()
    out["volatility_120"] = ret_1.rolling(120, min_periods=90).std()
    out["max_dd_60"] = _rolling_max_drawdown_series(close, 60)
    # Ranking-only diagnostics. They are intentionally absent from
    # CANDIDATE_FEATURES, so adding the portfolio layer cannot change fitting.
    out["max_drawdown_120"] = _rolling_max_drawdown_series(close, 120)

    prev_close = close.shift(1)
    true_range = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    atr14 = true_range.rolling(14, min_periods=14).mean()
    out["atr14_pct"] = atr14 / (close + EPS)
    out["atr_extension_20"] = (close - ma20) / (atr14 + EPS)

    prior_high55 = high.shift(1).rolling(55, min_periods=55).max()
    out["breakout_55"] = close / (prior_high55 + EPS) - 1
    high252 = high.rolling(252, min_periods=200).max()
    prior_high252 = high.shift(1).rolling(252, min_periods=200).max()
    out["distance_from_high_252"] = close / (high252 + EPS) - 1
    out["distance_from_prior_high_252"] = close / (prior_high252 + EPS) - 1

    # Accumulation/base features are scale-free and strictly backward-looking.
    # They describe a quiet, persistent base rather than simply rewarding a
    # stock that already has the strongest recent return.
    high60 = high.rolling(60, min_periods=45).max()
    low60 = low.rolling(60, min_periods=45).min()
    high120 = high.rolling(120, min_periods=90).max()
    low120 = low.rolling(120, min_periods=90).min()
    out["base_range_60"] = high60 / (low60 + EPS) - 1
    out["base_range_120"] = high120 / (low120 + EPS) - 1
    in_base_band = out["price_to_ma50"].abs().le(0.15).where(ma50.notna())
    out["base_stability_120"] = in_base_band.astype(float).rolling(
        120, min_periods=90
    ).mean()
    out["volatility_contraction_20_120"] = (
        out["volatility_20"] / (out["volatility_120"] + EPS)
    )
    atr14_pct_median60 = out["atr14_pct"].rolling(60, min_periods=45).median()
    out["atr_contraction_14_60"] = out["atr14_pct"] / (atr14_pct_median60 + EPS)
    intraday_range_pct = (high - low) / (close + EPS)
    range20 = intraday_range_pct.rolling(20, min_periods=15).mean()
    range120 = intraday_range_pct.rolling(120, min_periods=90).mean()
    out["range_contraction_20_120"] = range20 / (range120 + EPS)
    # Backward-compatible auxiliary used by the timing layer.
    out["base_contraction"] = out["volatility_20"] / (out["volatility_60"] + EPS)

    # Robust multi-scale liquidity regime.  Absolute traded value remains an
    # audit field; it is no longer a hard eligibility rule or an absolute model
    # input.  Every model feature below is relative or cross-sectional.
    nonzero_volume = volume.where(volume > 0)
    median_vol20 = nonzero_volume.rolling(20, min_periods=15).median()
    median_vol60 = nonzero_volume.rolling(60, min_periods=45).median()
    median_vol120 = nonzero_volume.rolling(120, min_periods=90).median()
    traded_value = close * volume * cfg.price_value_multiplier
    median_value20 = traded_value.where(traded_value > 0).rolling(20, min_periods=15).median()
    avg_value20 = traded_value.rolling(20, min_periods=20).mean()
    avg_value60 = traded_value.rolling(60, min_periods=45).mean()
    median_value60 = traded_value.where(traded_value > 0).rolling(60, min_periods=45).median()
    median_value120 = traded_value.where(traded_value > 0).rolling(120, min_periods=90).median()
    raw_volume_ratio20 = volume / (median_vol20 + 1)
    out["volume_ratio_short_long"] = (
        median_vol20 / (median_vol120 + 1)
    ).clip(0, cfg.max_volume_ratio_feature)
    high_volume_day = volume.gt(median_vol60).where(median_vol60.notna())
    out["volume_persistence_20"] = high_volume_day.astype(float).rolling(
        20, min_periods=15
    ).mean()
    up_volume60 = volume.where(ret_1.gt(0), 0.0).rolling(60, min_periods=45).sum()
    down_volume60 = volume.where(ret_1.lt(0), 0.0).rolling(60, min_periods=45).sum()
    out["up_down_volume_ratio_60"] = (
        up_volume60 / (down_volume60 + 1)
    ).clip(0, cfg.max_volume_ratio_feature)
    volume_log = np.log1p(volume.clip(lower=0))
    out["volume_trend_60"], _ = _rolling_trend_series(volume_log, 60)
    out["value_regime_20_120"] = (
        median_value20 / (median_value120 + 1)
    ).clip(0, cfg.max_volume_ratio_feature)

    # Auxiliary fields used by data-quality audit and entry timing, not by the
    # compact model feature set unless explicitly listed above.
    out["volume_ratio_20"] = raw_volume_ratio20.clip(0, cfg.max_volume_ratio_feature)
    out["value_ratio_20"] = (traded_value / (median_value20 + 1)).clip(0, cfg.max_volume_ratio_feature)
    out["log_value_traded_20"] = np.log1p(avg_value20.clip(lower=0))

    # Point-in-time quality fields.  These are NOT model features unless listed.
    out["observed_ratio_60"] = observed.astype(float).rolling(60, min_periods=60).mean()
    out["observed_ratio_120"] = observed.astype(float).rolling(120, min_periods=120).mean()
    out["zero_volume_ratio_60"] = volume.eq(0).rolling(60, min_periods=60).mean()
    out["median_value_traded_60"] = median_value60
    out["avg_value_traded_20"] = avg_value20
    out["avg_value_traded_60"] = avg_value60
    out["avg_volume_20"] = volume.rolling(20, min_periods=15).mean()
    out["avg_volume_60"] = volume.rolling(60, min_periods=45).mean()
    out["abnormal_volume_ratio_60"] = raw_volume_ratio20.gt(10.0).rolling(
        60, min_periods=45
    ).mean()
    out["history_sessions"] = np.arange(1, len(out) + 1)

    corp_jump = ret_1.abs().gt(cfg.corporate_action_jump)
    out["corp_action_recent"] = corp_jump.rolling(
        cfg.corporate_action_cooldown,
        min_periods=1,
    ).max().fillna(False).astype(bool)
    abnormal_volume = raw_volume_ratio20.gt(cfg.max_raw_volume_ratio)
    out["abnormal_volume_recent"] = abnormal_volume.rolling(
        cfg.abnormal_volume_cooldown,
        min_periods=1,
    ).max().fillna(False).astype(bool)

    out["quality_observed_candle"] = observed
    out["quality_history_ok"] = out["history_sessions"] >= cfg.min_history_sessions
    out["quality_observed_60_ok"] = out["observed_ratio_60"] >= cfg.min_observed_ratio_60
    out["quality_observed_120_ok"] = out["observed_ratio_120"] >= cfg.min_observed_ratio_120
    out["quality_zero_volume_ok"] = out["zero_volume_ratio_60"] <= cfg.max_zero_volume_ratio_60
    out["quality_corporate_action_ok"] = ~out["corp_action_recent"]
    out["quality_volume_anomaly_ok"] = ~out["abnormal_volume_recent"]
    quality_columns = [
        "quality_observed_candle",
        "quality_history_ok",
        "quality_observed_60_ok",
        "quality_observed_120_ok",
        "quality_zero_volume_ok",
        "quality_corporate_action_ok",
        "quality_volume_anomaly_ok",
    ]
    out["eligible"] = out[quality_columns].fillna(False).all(axis=1)
    return out


# ---------------------------------------------------------------------------
# Unbounded structural-event early-major-wave target
# ---------------------------------------------------------------------------

def _build_minmax_segment_tree(
    min_values: np.ndarray,
    max_values: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, int]:
    """Build min/max trees so bounded future-path queries remain O(n log n).

    ``min_values`` contains every executable close for the failure event.
    ``max_values`` may mask unconfirmed uptrend dates with NaN/-inf, so a mere
    one-day price spike cannot become a positive major-wave label.
    """
    if max_values is None:
        max_values = min_values
    if len(min_values) != len(max_values):
        raise ValueError("min_values and max_values must have equal length")
    n = len(min_values)
    size = 1
    while size < n:
        size <<= 1
    max_tree = np.full(2 * size, -np.inf, dtype=float)
    min_tree = np.full(2 * size, np.inf, dtype=float)
    min_finite = np.isfinite(min_values) & (min_values > 0)
    max_finite = np.isfinite(max_values) & (max_values > 0)
    max_tree[size:size + n] = np.where(max_finite, max_values, -np.inf)
    min_tree[size:size + n] = np.where(min_finite, min_values, np.inf)
    for node in range(size - 1, 0, -1):
        max_tree[node] = max(max_tree[2 * node], max_tree[2 * node + 1])
        min_tree[node] = min(min_tree[2 * node], min_tree[2 * node + 1])
    return min_tree, max_tree, size


def _first_structural_event_tree(
    min_tree: np.ndarray,
    max_tree: np.ndarray,
    tree_size: int,
    n: int,
    start_idx: int,
    up_level: float,
    down_level: float,
) -> tuple[int | None, int | None]:
    """Find the first confirmed wave/breakdown event without a time cutoff."""
    def search(node: int, left: int, right: int) -> int:
        if right <= start_idx or left >= n:
            return -1
        if max_tree[node] < up_level and min_tree[node] > down_level:
            return -1
        if right - left == 1:
            return left
        mid = (left + right) // 2
        hit = search(node * 2, left, mid)
        if hit >= 0:
            return hit
        return search(node * 2 + 1, mid, right)

    hit_idx = search(1, 0, tree_size)
    if hit_idx < 0:
        return None, None
    if max_tree[tree_size + hit_idx] >= up_level:
        return 1, hit_idx
    return 0, hit_idx


def _first_confirmed_wave_tree_bounded(
    max_tree: np.ndarray,
    tree_size: int,
    n: int,
    start_idx: int,
    stop_idx: int,
    up_level: float,
) -> int | None:
    """Bounded search used only for evaluation diagnostics, never the label."""
    def search(node: int, left: int, right: int) -> int:
        if right <= start_idx or left >= stop_idx or left >= n:
            return -1
        if max_tree[node] < up_level:
            return -1
        if right - left == 1:
            return left
        mid = (left + right) // 2
        hit = search(node * 2, left, mid)
        if hit >= 0:
            return hit
        return search(node * 2 + 1, mid, right)

    hit_idx = search(1, 0, tree_size)
    return None if hit_idx < 0 else hit_idx


def _range_max_tree(
    max_tree: np.ndarray,
    tree_size: int,
    start_idx: int,
    stop_idx: int,
) -> float:
    """Return the maximum finite value in ``[start_idx, stop_idx)`` in O(log n)."""
    left = start_idx + tree_size
    right = stop_idx + tree_size
    result = -np.inf
    while left < right:
        if left & 1:
            result = max(result, max_tree[left])
            left += 1
        if right & 1:
            right -= 1
            result = max(result, max_tree[right])
        left >>= 1
        right >>= 1
    return float(result) if np.isfinite(result) else np.nan


def add_strong_wave_targets(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Resolve an early-state episode with no fixed future horizon.

    A positive requires the return barrier on a persistent confirmed uptrend.
    A negative requires both a deep loss and a persistent confirmed downtrend;
    a temporary -25% touch therefore does not erase a later base/breakout path.
    If neither structural event occurs before the data end, the row is censored.
    """
    out = df.copy()
    n = len(out)
    labels = np.full(n, -1, dtype=np.int8)
    resolution_codes = np.full(n, -1, dtype=np.int8)
    labels_252 = np.full(n, -1, dtype=np.int8)
    raw_wave_252 = np.full(n, np.nan, dtype=float)
    entry_times = np.full(n, np.datetime64("NaT"), dtype="datetime64[ns]")
    label_end_times = np.full(n, np.datetime64("NaT"), dtype="datetime64[ns]")
    event_sessions = np.full(n, np.nan, dtype=float)
    event_returns = np.full(n, np.nan, dtype=float)
    label_relevance = np.ones(n, dtype=float)
    future_max_return_126 = np.full(n, np.nan, dtype=float)
    future_max_return_252 = np.full(n, np.nan, dtype=float)
    future_terminal_return_126 = np.full(n, np.nan, dtype=float)
    future_terminal_return_252 = np.full(n, np.nan, dtype=float)

    opens = out["open"].to_numpy(float)
    closes = out["close"].to_numpy(float)
    times = pd.to_datetime(out["time"]).to_numpy()
    observed = out["observed"].fillna(False).to_numpy(bool)

    # Next observed tradable row for each position, computed backward in O(n).
    next_obs = np.full(n, -1, dtype=int)
    next_idx = -1
    for i in range(n - 1, -1, -1):
        next_obs[i] = next_idx
        if observed[i] and np.isfinite(opens[i]) and opens[i] > 0:
            next_idx = i

    confirmation = (
        out["ret_60"].ge(cfg.confirmation_min_return_60) &
        out["slope_60"].ge(cfg.confirmation_min_slope_60) &
        out["trend_r2_60"].ge(cfg.confirmation_min_r2_60) &
        out["max_dd_60"].ge(cfg.confirmation_max_drawdown_60) &
        out["observed_ratio_60"].ge(cfg.confirmation_min_observed_ratio_60) &
        ~out["corp_action_recent"].fillna(True) &
        ~out["abnormal_volume_recent"].fillna(True)
    ).fillna(False).to_numpy(bool)
    out["major_wave_confirmed"] = confirmation
    major_wave_recent_60 = pd.Series(confirmation, index=out.index).rolling(
        60, min_periods=1
    ).max().fillna(0).astype(bool).to_numpy()
    out["major_wave_recent_60"] = major_wave_recent_60

    structural_failure = (
        out["ret_60"].le(cfg.failure_max_return_60) &
        out["slope_60"].le(cfg.failure_max_slope_60) &
        out["trend_r2_60"].ge(cfg.failure_min_r2_60) &
        out["observed_ratio_60"].ge(cfg.failure_min_observed_ratio_60) &
        ~out["corp_action_recent"].fillna(True) &
        ~out["abnormal_volume_recent"].fillna(True)
    ).fillna(False).to_numpy(bool)
    out["structural_failure_confirmed"] = structural_failure

    # Only confirmed event dates enter the event trees. The search itself has no
    # stop index, which is the core no-fixed-horizon label property.
    confirmed_closes = np.where(confirmation, closes, np.nan)
    failure_closes = np.where(structural_failure, closes, np.nan)
    failure_min_tree, confirmed_max_tree, tree_size = _build_minmax_segment_tree(
        failure_closes, confirmed_closes
    )
    _, raw_max_tree, _ = _build_minmax_segment_tree(closes, closes)
    valid_close_idx = np.where(observed & np.isfinite(closes) & (closes > 0), np.arange(n), -1)
    last_valid_close_idx = np.maximum.accumulate(valid_close_idx)

    # Target-side early-state gate. All inputs are available at date t. It is
    # deliberately broader than entry_quality so a valid breakout is not lost.
    pre_wave_state = (
        out["ret_60"].le(cfg.early_max_return_60) &
        out["ret_120"].le(cfg.early_max_return_120) &
        out["price_to_ma50"].le(cfg.early_max_price_to_ma50) &
        out["price_to_ma200"].le(cfg.early_max_price_to_ma200) &
        out["atr_extension_20"].le(cfg.early_max_atr_extension_20) &
        out["distance_from_prior_high_252"].le(cfg.early_max_breakout_prior_high_252) &
        ~pd.Series(major_wave_recent_60, index=out.index)
    ).fillna(False).to_numpy(bool)
    out["pre_wave_state"] = pre_wave_state

    eligible = out["eligible"].fillna(False).to_numpy(bool)
    for i in np.flatnonzero(eligible):
        entry_idx = next_obs[i]
        if entry_idx < 0:
            continue
        entry = opens[entry_idx]
        if not np.isfinite(entry) or entry <= 0:
            continue
        up_level = entry * (1.0 + cfg.strong_wave_return + cfg.round_trip_cost)
        down_level = entry * (1.0 + cfg.structural_failure_drawdown)
        entry_times[i] = times[entry_idx]

        event_label, hit_idx = _first_structural_event_tree(
            failure_min_tree,
            confirmed_max_tree,
            tree_size,
            n,
            entry_idx,
            up_level,
            down_level,
        )
        if event_label is not None and hit_idx is not None:
            labels[i] = int(event_label == 1 and pre_wave_state[i])
            resolution_codes[i] = (
                1 if labels[i] == 1 else (2 if event_label == 1 else 0)
            )
            label_end_times[i] = times[hit_idx]
            event_sessions[i] = int(hit_idx - entry_idx + 1)
            event_returns[i] = float(closes[hit_idx] / entry - 1.0 - cfg.round_trip_cost)
            if labels[i] == 1:
                decay = math.exp(
                    -math.log(2.0) * event_sessions[i] /
                    max(cfg.lead_time_half_life_sessions, 1)
                )
                label_relevance[i] = max(cfg.min_late_positive_relevance, decay)

        # Fixed windows below are outcomes for evaluation only. They never
        # decide wave_entry and may be unavailable near the snapshot end.
        stop_126 = entry_idx + 126
        stop_252 = entry_idx + 252
        if stop_126 <= n:
            future_max_return_126[i] = (
                _range_max_tree(raw_max_tree, tree_size, entry_idx, stop_126) / entry -
                1.0 - cfg.round_trip_cost
            )
            terminal_idx = last_valid_close_idx[stop_126 - 1]
            if terminal_idx >= entry_idx:
                future_terminal_return_126[i] = (
                    closes[terminal_idx] / entry - 1.0 - cfg.round_trip_cost
                )
        if stop_252 <= n:
            hit_252 = _first_confirmed_wave_tree_bounded(
                confirmed_max_tree, tree_size, n, entry_idx, stop_252, up_level
            )
            raw_wave_252[i] = float(hit_252 is not None)
            labels_252[i] = int(pre_wave_state[i] and hit_252 is not None)
            future_max_return_252[i] = (
                _range_max_tree(raw_max_tree, tree_size, entry_idx, stop_252) / entry -
                1.0 - cfg.round_trip_cost
            )
            terminal_idx = last_valid_close_idx[stop_252 - 1]
            if terminal_idx >= entry_idx:
                future_terminal_return_252[i] = (
                    closes[terminal_idx] / entry - 1.0 - cfg.round_trip_cost
                )

    out["wave_entry"] = pd.arrays.IntegerArray(labels, labels < 0)
    out["target_resolution"] = pd.Categorical.from_codes(
        resolution_codes + 1,
        categories=[
            "RIGHT_CENSORED",
            "STRUCTURAL_BREAKDOWN",
            "EARLY_CONFIRMED_WAVE",
            "ALREADY_EXTENDED_BEFORE_WAVE",
        ],
    )
    out["wave_entry_252"] = pd.arrays.IntegerArray(labels_252, labels_252 < 0)
    out["raw_confirmed_wave_252"] = raw_wave_252
    out["entry_time"] = pd.to_datetime(entry_times)
    out["label_end_time"] = pd.to_datetime(label_end_times)
    out["event_sessions"] = event_sessions
    out["event_return"] = event_returns
    out["label_relevance_weight"] = label_relevance
    out["future_max_return_126"] = future_max_return_126
    out["future_max_return_252"] = future_max_return_252
    out["future_terminal_return_126"] = future_terminal_return_126
    out["future_terminal_return_252"] = future_terminal_return_252
    return out


# ---------------------------------------------------------------------------
# Market / sector / leader context
# ---------------------------------------------------------------------------

def add_market_features(index_df: pd.DataFrame) -> pd.DataFrame:
    out = index_df[["time", "close"]].copy().sort_values("time")
    close = out["close"]
    ret1 = close.pct_change(fill_method=None)
    out["market_ret_20"] = close.pct_change(20, fill_method=None)
    out["market_ret_60"] = close.pct_change(60, fill_method=None)
    out["market_price_to_ma200"] = close / close.rolling(200, min_periods=200).mean() - 1
    out["market_volatility_20"] = ret1.rolling(20, min_periods=20).std()
    out["market_max_dd_60"] = _rolling_max_drawdown_series(close, 60)
    return out.drop(columns="close")


def enrich_cross_sectional_features(panel: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    out = panel.merge(market, on="time", how="left", validate="many_to_one")
    eligible = out.loc[out["eligible"].fillna(False)].copy()
    out["liquidity_percentile"] = out["median_value_traded_60"].where(
        out["eligible"].fillna(False)
    ).groupby(out["time"], observed=True).rank(pct=True)

    breadth = eligible.groupby("time", observed=True).agg(
        market_breadth_ma50=("above_ma50", "mean"),
        market_breadth_positive_20=(
            "ret_20", lambda s: float(s.dropna().gt(0).mean()) if s.notna().any() else np.nan
        ),
    ).reset_index()
    out = out.merge(breadth, on="time", how="left", validate="many_to_one")

    # Missing industry metadata must not turn the whole market into one fake
    # sector named UNKNOWN.  Market breadth/relative strength remain usable;
    # sector features stay NaN and are removed by train-only feature screening.
    sector_eligible = eligible.loc[eligible["industry_known"].fillna(False)].copy()
    sector_daily = sector_eligible.groupby(["industry", "time"], observed=True).agg(
        sector_ret_1=("ret_1", "mean"),
        sector_breadth_ma50=("above_ma50", "mean"),
    ).reset_index().sort_values(["industry", "time"])

    grouped = sector_daily.groupby("industry", observed=True, group_keys=False)
    sector_daily["sector_ret_20"] = grouped["sector_ret_1"].transform(
        lambda s: (1 + s.fillna(0)).rolling(20, min_periods=20).apply(np.prod, raw=True) - 1
    )
    sector_daily["sector_ret_60"] = grouped["sector_ret_1"].transform(
        lambda s: (1 + s.fillna(0)).rolling(60, min_periods=60).apply(np.prod, raw=True) - 1
    )
    sector_daily["sector_volatility_20"] = grouped["sector_ret_1"].transform(
        lambda s: s.rolling(20, min_periods=20).std()
    )
    sector_daily = sector_daily.merge(
        market[["time", "market_ret_60"]], on="time", how="left", validate="many_to_one"
    )
    sector_daily["sector_rs_60"] = sector_daily["sector_ret_60"] - sector_daily["market_ret_60"]
    sector_daily["sector_rank_60"] = sector_daily.groupby("time", observed=True)["sector_rs_60"].rank(pct=True)
    out = out.merge(
        sector_daily.drop(columns=["sector_ret_1", "market_ret_60"]),
        on=["industry", "time"], how="left", validate="many_to_one",
    )

    out["stock_rs_market_20"] = out["ret_20"] - out["market_ret_20"]
    out["stock_rs_market_60"] = out["ret_60"] - out["market_ret_60"]
    out["rs_improvement_20_vs_60"] = (
        out["stock_rs_market_20"] - out["stock_rs_market_60"]
    )
    out["rs_rank_market_60"] = out["stock_rs_market_60"].where(
        out["eligible"].fillna(False)
    ).groupby(out["time"], observed=True).rank(pct=True)
    out["rs_rank_change_20"] = out.groupby("ticker", observed=True)[
        "rs_rank_market_60"
    ].diff(20)
    sector_row_eligible = out["eligible"].fillna(False) & out["industry_known"].fillna(False)
    out["rs_rank_sector_60"] = out["stock_rs_market_60"].where(sector_row_eligible).groupby(
        [out["time"], out["industry"]], observed=True
    ).rank(pct=True)
    out["volume_rank_sector"] = out["volume_ratio_20"].where(sector_row_eligible).groupby(
        [out["time"], out["industry"]], observed=True
    ).rank(pct=True)
    out["leader_score"] = (
        0.55 * out["rs_rank_sector_60"] +
        0.25 * out["volume_rank_sector"] +
        0.20 * out["sector_rank_60"]
    )
    return out


# ---------------------------------------------------------------------------
# Snapshot build and point-in-time quality audit
# ---------------------------------------------------------------------------

def build_panel(
    cfg: Config,
    allow_stale_cache: bool = False,
    *,
    include_targets: bool = True,
) -> tuple[pd.DataFrame, dict[str, Any], pd.DataFrame]:
    """Build the point-in-time feature panel.

    ``include_targets=False`` is the production inference path.  It deliberately
    avoids calculating any future outcome or label, so an as-of snapshot cannot
    leak data that was unavailable at scoring time.
    """
    data_dir = Path(cfg.data_dir)
    manifest_path = data_dir / "snapshot_manifest.json"
    manifest: dict[str, Any] | None = None
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            if not allow_stale_cache:
                raise RuntimeError(f"Invalid snapshot manifest: {exc}") from exc
    elif not allow_stale_cache:
        raise RuntimeError("Missing snapshot_manifest.json; run the adapter sync first.")
    else:
        warnings.warn(
            "snapshot_manifest.json is absent; using the CSV files already present "
            f"in {data_dir} because --allow-stale-cache was supplied. No data will be downloaded.",
            RuntimeWarning,
        )

    if manifest is not None:
        coverage = float(manifest.get("coverage_ratio", 0.0))
        if coverage < cfg.min_snapshot_coverage and not allow_stale_cache:
            raise RuntimeError(f"Snapshot coverage {coverage:.1%} < {cfg.min_snapshot_coverage:.1%}")
        alignment_summary = manifest.get("calendar_alignment_summary", {})
        aligned_ratio = alignment_summary.get("current_to_vnindex_ratio")
        if (
            aligned_ratio is not None and
            float(aligned_ratio) < cfg.min_snapshot_coverage and
            not allow_stale_cache
        ):
            raise RuntimeError(
                f"Only {float(aligned_ratio):.1%} of symbols are current to the VNINDEX "
                "calendar; refresh the complete snapshot."
            )
        requested_as_of = pd.to_datetime(
            manifest.get("requested_as_of_end"), errors="coerce"
        )
        today = pd.Timestamp.now().normalize()
        if pd.isna(requested_as_of) and not allow_stale_cache:
            raise RuntimeError("Snapshot manifest has no valid requested_as_of_end.")
        if not pd.isna(requested_as_of) and not allow_stale_cache:
            age_days = int((today - pd.Timestamp(requested_as_of).normalize()).days)
            if age_days > cfg.freshness_days:
                raise RuntimeError(
                    f"Snapshot as-of date is {age_days} calendar days old; refresh the live universe."
                )
            if age_days < -1:
                raise RuntimeError("Snapshot as-of date is unexpectedly in the future.")
        price_policy = manifest.get("price_adjustment_policy")
        if price_policy not in {"raw", "adjusted"} and not allow_stale_cache:
            raise RuntimeError(
                "Snapshot price policy is unverified. Re-sync with --price-policy raw or adjusted."
            )
        manifest_multiplier = manifest.get("price_value_multiplier")
        if manifest_multiplier is None and not allow_stale_cache:
            raise RuntimeError(
                "Snapshot manifest does not declare price_value_multiplier; re-sync with adapter v3."
            )
        if manifest_multiplier is not None and not math.isclose(
            float(manifest_multiplier), cfg.price_value_multiplier, rel_tol=0, abs_tol=EPS
        ) and not allow_stale_cache:
            raise RuntimeError(
                f"Snapshot price_value_multiplier={manifest_multiplier} but trainer uses "
                f"{cfg.price_value_multiplier}. Make the liquidity units consistent."
            )
        symbol_records = manifest.get("symbols", {})
        successful = {
            str(symbol).upper(): record for symbol, record in symbol_records.items()
            if isinstance(record, dict) and record.get("status") == "ok"
        }
        files = [data_dir / f"{symbol}.csv" for symbol in sorted(successful)]
        integrity_errors: list[str] = []
        for path in files:
            record = successful[path.stem.upper()]
            expected = record.get("sha256")
            if not path.is_file():
                integrity_errors.append(f"missing:{path.name}")
            elif expected and file_sha256(path) != expected:
                integrity_errors.append(f"hash:{path.name}")
        if integrity_errors and not allow_stale_cache:
            raise RuntimeError("Snapshot integrity failed: " + ", ".join(integrity_errors[:10]))
        artifact_checks = (
            (Path(cfg.market_path), manifest.get("vnindex", {}), "vnindex"),
            (Path(cfg.industry_path), manifest.get("industry_map", {}), "industry_map"),
            (data_dir / "symbols.csv", manifest.get("equity_list", {}), "equity_list"),
        )
        for artifact_path, record, label in artifact_checks:
            expected = record.get("sha256") if isinstance(record, dict) else None
            if not artifact_path.is_file():
                integrity_errors.append(f"missing:{label}:{artifact_path}")
            elif not expected:
                integrity_errors.append(f"missing_hash:{label}")
            elif file_sha256(artifact_path) != expected:
                integrity_errors.append(f"hash:{label}:{artifact_path.name}")
        if integrity_errors and not allow_stale_cache:
            raise RuntimeError("Snapshot integrity failed: " + ", ".join(integrity_errors[:10]))
        files = [p for p in files if p.is_file()]
    else:
        files = sorted(
            p for p in data_dir.glob("*.csv") if p.name.lower() not in {"industry_map.csv", "symbols.csv"}
        )

    freshness = cache_freshness(files, cfg)
    if freshness["fresh_symbols"] < cfg.min_fresh_symbols and not allow_stale_cache:
        raise RuntimeError(
            f"Only {freshness['fresh_symbols']} fresh symbols; refresh the complete universe."
        )

    market_raw = load_ohlcv(Path(cfg.market_path))
    market = add_market_features(market_raw)
    industries = load_industry_map(Path(cfg.industry_path))
    if not industries and not allow_stale_cache:
        raise RuntimeError("Industry map is required. Sync with a stable ICB level (e.g. --icb-level 2).")
    if not industries and allow_stale_cache:
        warnings.warn(
            f"Industry map not found at {cfg.industry_path}; existing OHLCV files will still be "
            "used, while sector-context features and the sector-rotation ranking component "
            "remain neutral/unavailable.",
            RuntimeWarning,
        )
    industry_coverage = sum(path.stem.upper() in industries for path in files) / max(len(files), 1)
    if industry_coverage < cfg.min_industry_coverage and not allow_stale_cache:
        raise RuntimeError(
            f"Industry coverage {industry_coverage:.1%} < {cfg.min_industry_coverage:.1%}"
        )

    rows: list[pd.DataFrame] = []
    quality_rows: list[dict[str, Any]] = []
    failures: dict[str, str] = {}
    for pos, path in enumerate(files, 1):
        ticker = path.stem.upper()
        try:
            raw = load_ohlcv(path)
            aligned = align_stock_to_market_calendar(raw, market_raw["time"])
            if len(aligned) < cfg.min_history_sessions:
                quality_rows.append({"ticker": ticker, "status": "too_short", "rows": len(aligned)})
                continue
            stock = add_stock_features(aligned, cfg)
            if include_targets:
                stock = add_strong_wave_targets(stock, cfg)
            stock["ticker"] = ticker
            stock["industry"] = industries.get(ticker, "UNKNOWN")
            stock["industry_known"] = ticker in industries
            rows.append(stock)

            latest = stock.iloc[-1]
            quality_rows.append({
                "ticker": ticker,
                "status": "loaded",
                "rows": int(len(stock)),
                "latest_date": str(pd.Timestamp(latest["time"]).date()),
                "latest_eligible": bool(latest.get("eligible", False)),
                "observed_ratio_60": float(latest.get("observed_ratio_60", np.nan)),
                "observed_ratio_120": float(latest.get("observed_ratio_120", np.nan)),
                "zero_volume_ratio_60": float(latest.get("zero_volume_ratio_60", np.nan)),
                "median_value_traded_60": float(latest.get("median_value_traded_60", np.nan)),
                "avg_value_traded_20": float(latest.get("avg_value_traded_20", np.nan)),
                "corp_action_recent": bool(latest.get("corp_action_recent", False)),
                "abnormal_volume_recent": bool(latest.get("abnormal_volume_recent", False)),
                "resolved_positive_rate": (
                    float(stock["wave_entry"].dropna().astype(float).mean())
                    if include_targets and stock["wave_entry"].notna().any() else np.nan
                ),
                "resolved_labels": int(stock["wave_entry"].notna().sum()) if include_targets else 0,
            })
        except Exception as exc:
            failures[ticker] = f"{type(exc).__name__}: {exc}"
            quality_rows.append({"ticker": ticker, "status": "error", "error": failures[ticker]})
        if pos % 100 == 0:
            print(f"Loaded {pos}/{len(files)}; usable={len(rows)}; failed={len(failures)}")

    if not rows:
        raise RuntimeError("No stock data survived the data-quality pipeline")
    panel = pd.concat(rows, ignore_index=True, sort=False)
    panel = enrich_cross_sectional_features(panel, market)
    panel.replace([np.inf, -np.inf], np.nan, inplace=True)

    meta = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "freshness": freshness,
        "loaded_symbols": int(panel["ticker"].nunique()),
        "industry_coverage": industry_coverage,
        "failed_symbols": len(failures),
        "failure_sample": dict(list(failures.items())[:25]),
        "date_min": str(panel["time"].min().date()),
        "date_max": str(panel["time"].max().date()),
        "candidate_features": CANDIDATE_FEATURES,
        "target_definition": {
            "type": "unbounded_early_major_wave_vs_confirmed_structural_breakdown",
            "strong_wave_return": cfg.strong_wave_return,
            "round_trip_cost": cfg.round_trip_cost,
            "fixed_label_horizon": None,
            "positive_confirmation": {
                "min_return_60": cfg.confirmation_min_return_60,
                "min_slope_60": cfg.confirmation_min_slope_60,
                "min_trend_r2_60": cfg.confirmation_min_r2_60,
                "max_drawdown_60": cfg.confirmation_max_drawdown_60,
                "min_observed_ratio_60": cfg.confirmation_min_observed_ratio_60,
            },
            "early_state_gate": {
                "max_return_60": cfg.early_max_return_60,
                "max_return_120": cfg.early_max_return_120,
                "max_price_to_ma50": cfg.early_max_price_to_ma50,
                "max_price_to_ma200": cfg.early_max_price_to_ma200,
                "max_atr_extension_20": cfg.early_max_atr_extension_20,
                "max_breakout_prior_high_252": cfg.early_max_breakout_prior_high_252,
                "no_confirmed_major_wave_in_previous_sessions": 60,
            },
            "negative_confirmation": {
                "drawdown_from_entry": cfg.structural_failure_drawdown,
                "max_return_60": cfg.failure_max_return_60,
                "max_slope_60": cfg.failure_max_slope_60,
                "min_trend_r2_60": cfg.failure_min_r2_60,
                "min_observed_ratio_60": cfg.failure_min_observed_ratio_60,
            },
            "late_positive_relevance": {
                "half_life_sessions": cfg.lead_time_half_life_sessions,
                "minimum_weight": cfg.min_late_positive_relevance,
                "policy": "positive_label_is_retained_but_smoothly_downweighted",
            },
            "interim_drawdown_policy": (
                "temporary_drawdown_does_not_terminate; only confirmed structural breakdown does"
            ),
            "unresolved_rows": "right_censored_at_snapshot_end_and_excluded",
            "targets_calculated": include_targets,
            "evaluation_only_horizons": [126, 252],
        },
        "liquidity_value_multiplier": cfg.price_value_multiplier,
    }
    if manifest is not None:
        meta["snapshot_manifest"] = manifest
    return panel.sort_values(["time", "ticker"]).reset_index(drop=True), meta, pd.DataFrame(quality_rows)


def prepare_samples(panel: pd.DataFrame, cfg: Config) -> tuple[pd.DataFrame, pd.DataFrame]:
    # In explicitly allowed legacy/debug snapshots an industry map may be absent.
    # Do not fail every row merely because an entire optional feature family is
    # unavailable; the train-only processor will record and drop that family.
    eligible_panel = panel.loc[panel["eligible"].fillna(False)]
    available = [
        feature for feature in CANDIDATE_FEATURES
        if eligible_panel[feature].notna().mean() >= (1.0 - cfg.max_feature_missing_rate)
    ]
    if len(available) < 12:
        raise RuntimeError(
            f"Only {len(available)} candidate features have usable panel coverage; inspect the snapshot."
        )
    coverage = panel[available].notna().mean(axis=1)
    common = panel["eligible"].fillna(False) & (coverage >= cfg.min_row_feature_coverage)
    ordered_dates = pd.Index(sorted(panel["time"].dropna().unique()))
    if cfg.supervised_sample_anchor_date is not None:
        anchor = pd.Timestamp(cfg.supervised_sample_anchor_date).normalize()
        if anchor not in ordered_dates:
            raise ValueError(
                "supervised_sample_anchor_date must be a market date in the panel"
            )
        date_position = panel["time"].map(
            {date: pos for pos, date in enumerate(ordered_dates)}
        )
        anchor_position = int(ordered_dates.get_loc(anchor))
        supervised_date = date_position.subtract(anchor_position).mod(
            max(cfg.supervised_sample_stride, 1)
        ).eq(0)
    elif cfg.supervised_sample_weekday is None:
        sampled_dates = ordered_dates
        date_position = panel["time"].map(
            {date: pos for pos, date in enumerate(sampled_dates)}
        )
        supervised_date = date_position.mod(max(cfg.supervised_sample_stride, 1)).eq(0)
    else:
        if not 0 <= int(cfg.supervised_sample_weekday) <= 4:
            raise ValueError("supervised_sample_weekday must be in [0, 4]")
        sampled_dates = ordered_dates[
            pd.to_datetime(ordered_dates).weekday == int(cfg.supervised_sample_weekday)
        ]
        date_position = panel["time"].map(
            {date: pos for pos, date in enumerate(sampled_dates)}
        )
        supervised_date = date_position.notna() & date_position.mod(
            max(cfg.supervised_sample_stride, 1)
        ).eq(0)
    labelled = panel.loc[
        common & supervised_date & panel["wave_entry"].notna() & panel["label_end_time"].notna()
    ].copy()
    labelled["wave_entry"] = labelled["wave_entry"].astype(int)
    # Current inference includes eligible unresolved rows, especially the latest date.
    unlabelled = panel.loc[common & panel["wave_entry"].isna()].copy()
    return (
        labelled.sort_values(["time", "ticker"]).reset_index(drop=True),
        unlabelled.sort_values(["time", "ticker"]).reset_index(drop=True),
    )


# ---------------------------------------------------------------------------
# Date splits and event weighting
# ---------------------------------------------------------------------------

def effective_sample_stride_sessions(cfg: Config) -> int:
    """Return the approximate market-session spacing of supervised samples."""
    # A weekday calendar selects one observation from roughly every five market
    # sessions before applying the configured stride among those dates. An
    # explicit anchor already operates on the full market calendar.
    weekday_factor = 5 if (
        cfg.supervised_sample_weekday is not None
        and cfg.supervised_sample_anchor_date is None
    ) else 1
    return max(int(cfg.supervised_sample_stride), 1) * weekday_factor


def nested_calibration_split(
    fold_train: pd.DataFrame, cfg: Config
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reserve a recent causal calibration block containing both classes.

    Weekly calendars can have a long run without a positive event.  A fixed
    number of snapshots would then make an otherwise valid fold unusable, so
    the recent block expands backward until both the training core and the
    calibration block contain both classes.
    """
    dates = np.array(sorted(fold_train["time"].unique()))
    snapshots = max(
        8,
        int(math.ceil(cfg.ablation_calibration_sessions / effective_sample_stride_sessions(cfg))),
    )
    while snapshots < len(dates):
        calibration_start = pd.Timestamp(dates[-snapshots])
        core = fold_train.loc[
            (fold_train["time"] < calibration_start)
            & (fold_train["label_end_time"] < calibration_start)
        ].copy()
        calibration = fold_train.loc[fold_train["time"] >= calibration_start].copy()
        if (
            not core.empty
            and not calibration.empty
            and core["wave_entry"].nunique() >= 2
            and calibration["wave_entry"].nunique() >= 2
        ):
            return core, calibration
        next_snapshots = min(len(dates) - 1, max(snapshots + 1, snapshots * 2))
        if next_snapshots <= snapshots:
            break
        snapshots = next_snapshots
    raise RuntimeError(
        "Nested calibration cannot obtain two classes without exhausting the fold"
    )

def split_train_calibration_test(
    labelled: pd.DataFrame,
    all_market_dates: np.ndarray,
    cfg: Config,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, str]]:
    dates = np.array(sorted(pd.to_datetime(all_market_dates)))
    required = (
        cfg.min_cv_train_sessions + cfg.cv_splits * cfg.min_cv_validation_sessions +
        cfg.calibration_sessions + cfg.test_sessions + cfg.evaluation_maturity_sessions
    )
    if len(dates) < required:
        raise RuntimeError(f"Only {len(dates)} market dates; need at least {required}.")

    maturity_start_pos = len(dates) - cfg.evaluation_maturity_sessions
    test_start_pos = maturity_start_pos - cfg.test_sessions
    cal_start_pos = test_start_pos - cfg.calibration_sessions
    calibration_start = pd.Timestamp(dates[cal_start_pos])
    test_start = pd.Timestamp(dates[test_start_pos])
    maturity_start = pd.Timestamp(dates[maturity_start_pos])

    train = labelled.loc[
        (labelled["time"] < calibration_start) &
        (labelled["label_end_time"] < calibration_start)
    ].copy()
    calibration = labelled.loc[
        (labelled["time"] >= calibration_start) &
        (labelled["time"] < test_start) &
        (labelled["label_end_time"] < test_start)
    ].copy()
    test = labelled.loc[
        (labelled["time"] >= test_start) &
        (labelled["time"] < maturity_start) &
        (labelled["label_end_time"] <= pd.Timestamp(dates[-1]))
    ].copy()

    for name, frame in (("train", train), ("calibration", calibration), ("test", test)):
        if frame.empty or frame["wave_entry"].nunique() < 2:
            raise RuntimeError(f"{name} split is empty or contains only one class")

    boundaries = {
        "calibration_start": str(calibration_start.date()),
        "test_start": str(test_start.date()),
        "evaluation_maturity_start": str(maturity_start.date()),
        "data_end": str(pd.Timestamp(dates[-1]).date()),
        "label_horizon": "unbounded_first_confirmed_structural_event",
        "train_last_label_end": str(train["label_end_time"].max().date()),
        "calibration_last_label_end": str(calibration["label_end_time"].max().date()),
    }
    return train, calibration, test, boundaries


def purged_walk_forward_folds(
    train: pd.DataFrame, cfg: Config
) -> list[tuple[np.ndarray, np.ndarray, dict[str, str]]]:
    dates = np.array(sorted(train["time"].unique()))
    stride = effective_sample_stride_sessions(cfg)
    first_validation_pos = math.ceil(cfg.min_cv_train_sessions / stride)
    min_validation_snapshots = math.ceil(cfg.min_cv_validation_sessions / stride)
    remaining = len(dates) - first_validation_pos
    if remaining < cfg.cv_splits * min_validation_snapshots:
        raise RuntimeError("Not enough training dates for requested walk-forward folds")
    validation_size = remaining // cfg.cv_splits
    folds: list[tuple[np.ndarray, np.ndarray, dict[str, str]]] = []
    for fold in range(cfg.cv_splits):
        start_pos = first_validation_pos + fold * validation_size
        end_pos = len(dates) if fold == cfg.cv_splits - 1 else start_pos + validation_size
        validation_start = pd.Timestamp(dates[start_pos])
        validation_end_exclusive = pd.Timestamp(dates[end_pos]) if end_pos < len(dates) else pd.Timestamp.max
        train_mask = (
            (train["time"] < validation_start) &
            (train["label_end_time"] < validation_start)
        ).to_numpy()
        val_mask = (
            (train["time"] >= validation_start) &
            (train["time"] < validation_end_exclusive)
        ).to_numpy()
        train_idx, val_idx = np.flatnonzero(train_mask), np.flatnonzero(val_mask)
        if train_idx.size == 0 or val_idx.size == 0:
            continue
        if train.iloc[train_idx]["wave_entry"].nunique() < 2 or train.iloc[val_idx]["wave_entry"].nunique() < 2:
            continue
        folds.append((train_idx, val_idx, {
            "fold": str(fold + 1),
            "validation_start": str(validation_start.date()),
            "validation_end": str(train.iloc[val_idx]["time"].max().date()),
            "train_last_label_end": str(train.iloc[train_idx]["label_end_time"].max().date()),
        }))
    if len(folds) < 2:
        raise RuntimeError("Fewer than two valid purged walk-forward folds were produced")
    return folds


def event_uniqueness_weights(frame: pd.DataFrame) -> np.ndarray:
    ordered = frame.sort_values(["ticker", "time"])
    y_ordered = ordered["wave_entry"].to_numpy(int)
    previous = ordered.groupby("ticker", observed=True)["wave_entry"].shift()
    new_run = ordered["wave_entry"].ne(previous)
    run_id = new_run.groupby(ordered["ticker"]).cumsum()
    run_size = ordered.groupby([ordered["ticker"], run_id], observed=True)["wave_entry"].transform("size").to_numpy(float)
    relevance = pd.to_numeric(
        ordered.get("label_relevance_weight", 1.0), errors="coerce"
    )
    if np.isscalar(relevance):
        relevance_values = np.ones(len(ordered), dtype=float)
    else:
        relevance_values = relevance.fillna(1.0).clip(lower=0.0, upper=1.0).to_numpy(float)
    event_weight_ordered = (
        np.where(y_ordered == 1, 1.0 / np.maximum(run_size, 1), 1.0) *
        relevance_values
    )
    return pd.Series(event_weight_ordered, index=ordered.index).reindex(frame.index).to_numpy(float)


def date_balanced_weights(frame: pd.DataFrame) -> np.ndarray:
    """Give every snapshot equal mass, with smooth late-event relevance decay."""
    relevance = np.ones(len(frame), dtype=float)
    if "label_relevance_weight" in frame:
        relevance = pd.to_numeric(
            frame["label_relevance_weight"], errors="coerce"
        ).fillna(1.0).clip(lower=0.0, upper=1.0).to_numpy(float)
    relevance_series = pd.Series(relevance, index=frame.index)
    date_mass = relevance_series.groupby(frame["time"], observed=True).transform("sum").to_numpy(float)
    weights = relevance / np.maximum(date_mass, EPS)
    return weights / max(float(weights.mean()), EPS)


def balanced_event_weights(frame: pd.DataFrame) -> np.ndarray:
    event_weight = event_uniqueness_weights(frame)
    y = frame["wave_entry"].to_numpy(int)
    negatives = max(int((1 - y).sum()), 1)
    positive_mass = max(float(event_weight[y == 1].sum()), 1.0)
    class_multiplier = negatives / positive_mass
    weights = event_weight * np.where(y == 1, class_multiplier, 1.0)
    return weights / max(weights.mean(), EPS)


# ---------------------------------------------------------------------------
# Train-only feature screening / clipping / imputation
# ---------------------------------------------------------------------------

def fit_feature_processor(
    train: pd.DataFrame,
    cfg: Config,
    candidate_features: Iterable[str] | None = None,
) -> dict[str, Any]:
    candidates = list(dict.fromkeys(candidate_features or CANDIDATE_FEATURES))
    sample = train[candidates]
    if len(sample) > cfg.feature_screen_sample:
        sample = sample.sample(cfg.feature_screen_sample, random_state=cfg.random_seed)

    feature_rows: list[dict[str, Any]] = []
    kept: list[str] = []
    medians: dict[str, float] = {}
    lows: dict[str, float] = {}
    highs: dict[str, float] = {}

    for feature in candidates:
        series = pd.to_numeric(sample[feature], errors="coerce").replace([np.inf, -np.inf], np.nan)
        missing_rate = float(series.isna().mean())
        nunique = int(series.nunique(dropna=True))
        is_binary = feature.startswith("sig_")
        reason = "keep"
        if missing_rate > cfg.max_feature_missing_rate:
            reason = "drop_missing"
        elif nunique < (2 if is_binary else cfg.min_feature_unique_values):
            reason = "drop_low_variance"
        if reason == "keep":
            finite = series.dropna()
            median = float(finite.median()) if not finite.empty else 0.0
            low = float(finite.quantile(cfg.clip_quantile_low)) if not is_binary and not finite.empty else -1.0
            high = float(finite.quantile(cfg.clip_quantile_high)) if not is_binary and not finite.empty else 1.0
            if not np.isfinite(low):
                low = median
            if not np.isfinite(high):
                high = median
            if low > high:
                low, high = high, low
            medians[feature], lows[feature], highs[feature] = median, low, high
            kept.append(feature)
        feature_rows.append({
            "feature": feature, "missing_rate": missing_rate, "nunique": nunique,
            "decision": reason,
        })

    # Remove extreme redundancy using train-only Spearman correlation.
    continuous = [f for f in kept if not f.startswith("sig_")]
    dropped_corr: dict[str, str] = {}
    if len(continuous) > 1:
        corr_input = sample[continuous].copy()
        for f in continuous:
            corr_input[f] = pd.to_numeric(corr_input[f], errors="coerce").fillna(medians[f]).clip(lows[f], highs[f])
        corr = corr_input.corr(method="spearman").abs()
        final_continuous: list[str] = []
        for feature in continuous:
            conflict = next(
                (kept_feature for kept_feature in final_continuous
                 if np.isfinite(corr.loc[feature, kept_feature]) and corr.loc[feature, kept_feature] >= cfg.max_pairwise_abs_spearman),
                None,
            )
            if conflict is None:
                final_continuous.append(feature)
            else:
                dropped_corr[feature] = conflict
        kept = [f for f in kept if f.startswith("sig_") or f in final_continuous]

    decisions = pd.DataFrame(feature_rows)
    if dropped_corr:
        mask = decisions["feature"].isin(dropped_corr)
        decisions.loc[mask, "decision"] = decisions.loc[mask, "feature"].map(
            lambda f: f"drop_corr_with:{dropped_corr[f]}"
        )
    if len(kept) < cfg.min_selected_features:
        raise RuntimeError(f"Only {len(kept)} features survived train-only screening; inspect data quality.")

    return {
        "features": kept,
        "candidate_features": candidates,
        "medians": {f: medians[f] for f in kept},
        "clip_low": {f: lows[f] for f in kept},
        "clip_high": {f: highs[f] for f in kept},
        "quality_table": decisions,
    }


def transform_features(frame: pd.DataFrame, processor: dict[str, Any]) -> np.ndarray:
    features = processor["features"]
    X = np.empty((len(frame), len(features)), dtype=np.float32)
    for j, feature in enumerate(features):
        values = pd.to_numeric(frame[feature], errors="coerce").to_numpy(float)
        values[~np.isfinite(values)] = processor["medians"][feature]
        if not feature.startswith("sig_"):
            values = np.clip(values, processor["clip_low"][feature], processor["clip_high"][feature])
        X[:, j] = values.astype(np.float32)
    return X


# ---------------------------------------------------------------------------
# Models, tuning, calibration, ensemble
# ---------------------------------------------------------------------------

def suggest_classifier_params(model_name: str, trial: optuna.Trial) -> dict[str, Any]:
    n_estimators = trial.suggest_int("n_estimators", 200, 600)
    max_depth = trial.suggest_int("max_depth", 3, 7)
    learning_rate = trial.suggest_float("learning_rate", 0.015, 0.10, log=True)
    if model_name == "xgb":
        return {
            "n_estimators": n_estimators, "max_depth": max_depth, "learning_rate": learning_rate,
            "min_child_weight": trial.suggest_float("min_child_weight", 2, 20),
            "subsample": trial.suggest_float("subsample", 0.65, 0.95),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.60, 0.95),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-4, 3.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 0.1, 8.0, log=True),
            "gamma": trial.suggest_float("gamma", 0.0, 2.0),
        }
    if model_name == "lgb":
        return {
            "n_estimators": n_estimators, "max_depth": max_depth, "learning_rate": learning_rate,
            "num_leaves": trial.suggest_int("num_leaves", 15, 63),
            "min_child_samples": trial.suggest_int("min_child_samples", 30, 200),
            "subsample": trial.suggest_float("subsample", 0.65, 0.95),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.60, 0.95),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-4, 3.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 0.1, 8.0, log=True),
        }
    if model_name == "cat":
        return {
            "iterations": n_estimators, "depth": max_depth, "learning_rate": learning_rate,
            "l2_leaf_reg": trial.suggest_float("l2_leaf_reg", 1.0, 15.0),
            "random_strength": trial.suggest_float("random_strength", 0.0, 2.0),
            "bagging_temperature": trial.suggest_float("bagging_temperature", 0.0, 2.0),
        }
    raise KeyError(model_name)


def make_classifier(
    model_name: str,
    params: dict[str, Any],
    seed: int,
    compute_device: str = "cpu",
):
    if compute_device not in {"cpu", "cuda"}:
        raise ValueError(f"Unsupported compute_device: {compute_device}")
    if model_name == "xgb":
        return XGBClassifier(
            **params, objective="binary:logistic", eval_metric="logloss",
            random_state=seed, n_jobs=-1, tree_method="hist",
            device="cuda" if compute_device == "cuda" else "cpu",
        )
    if model_name == "lgb":
        return LGBMClassifier(
            **params, subsample_freq=1, random_state=seed, n_jobs=-1, verbosity=-1,
        )
    if model_name == "cat":
        gpu_options = {"task_type": "GPU", "devices": "0"} if compute_device == "cuda" else {}
        return CatBoostClassifier(
            **params, random_seed=seed, verbose=False, allow_writing_files=False,
            **gpu_options,
        )
    raise KeyError(model_name)


def tune_classifier(
    model_name: str,
    train: pd.DataFrame,
    folds: list[tuple[np.ndarray, np.ndarray, dict[str, str]]],
    candidate_features: Iterable[str],
    cfg: Config,
) -> tuple[dict[str, Any], dict[str, Any]]:
    # Each fold owns its feature screening/clipping/imputation fit. Reusing a
    # processor fitted on all TRAIN dates would leak later fold distributions.
    fold_inputs: list[dict[str, Any]] = []
    for train_idx, val_idx, fold_meta in folds:
        fold_train = train.iloc[train_idx]
        validation = train.iloc[val_idx]
        fold_processor = fit_feature_processor(fold_train, cfg, candidate_features)
        fold_inputs.append({
            "fold_train": fold_train,
            "validation": validation,
            "X_train": transform_features(fold_train, fold_processor),
            "X_validation": transform_features(validation, fold_processor),
            "y_train": fold_train["wave_entry"].to_numpy(int),
            "y_validation": validation["wave_entry"].to_numpy(int),
            "meta": fold_meta,
        })

    def objective(trial: optuna.Trial) -> float:
        params = suggest_classifier_params(model_name, trial)
        scores: list[float] = []
        for fold_input in fold_inputs:
            fold_train = fold_input["fold_train"]
            validation = fold_input["validation"]
            model = make_classifier(model_name, params, cfg.random_seed, cfg.compute_device)
            model.fit(
                fold_input["X_train"],
                fold_input["y_train"],
                sample_weight=balanced_event_weights(fold_train),
            )
            probability = model.predict_proba(fold_input["X_validation"])[:, 1]
            validation_weight = event_uniqueness_weights(validation)
            y_validation = fold_input["y_validation"]
            base_rate = float(np.average(y_validation, weights=validation_weight))
            pr_auc = average_precision_score(
                y_validation, probability, sample_weight=validation_weight
            )
            top_lift = precision_at_k_by_date(
                validation, probability, cfg.top_k_per_day, validation_weight
            )["lift_at_k"]
            score = (
                0.70 * math.log(max(pr_auc / max(base_rate, EPS), EPS)) +
                0.30 * math.log(max(top_lift, EPS))
            )
            scores.append(float(score))
        trial.set_user_attr("fold_scores", scores)
        # Reward ranking signal, penalise unstable hyperparameters across time.
        return float(np.mean(scores) - 0.15 * np.std(scores))

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=cfg.random_seed),
        study_name=f"wave_v6_{model_name}",
    )
    study.optimize(objective, n_trials=cfg.optuna_trials, show_progress_bar=True)
    best_params = suggest_classifier_params(model_name, optuna.trial.FixedTrial(study.best_params))
    return best_params, {
        "best_objective": float(study.best_value),
        "best_fold_scores": [float(x) for x in study.best_trial.user_attrs.get("fold_scores", [])],
        "trials": cfg.optuna_trials,
    }


def fit_models(
    frame: pd.DataFrame,
    params: dict[str, dict[str, Any]],
    processor: dict[str, Any],
    cfg: Config,
) -> dict[str, Any]:
    X = transform_features(frame, processor)
    y = frame["wave_entry"].to_numpy(int)
    weights = balanced_event_weights(frame)
    models: dict[str, Any] = {}
    for name in MODEL_NAMES:
        model = make_classifier(name, params[name], cfg.random_seed, cfg.compute_device)
        model.fit(X, y, sample_weight=weights)
        models[name] = model
    return models


def walk_forward_model_diagnostics(
    train: pd.DataFrame,
    folds: list[tuple[np.ndarray, np.ndarray, dict[str, str]]],
    best_params: dict[str, dict[str, Any]],
    candidate_features: Iterable[str],
    cfg: Config,
    prediction_output: Path | None = None,
    anchor_frame: pd.DataFrame | None = None,
    anchor_prediction_output: Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Measure stability and optionally export strictly causal base predictions.

    The optional export is deliberately produced from the same fold-local
    models used by the diagnostics.  It is therefore safe as the original V6
    pre-breakdown trend input to the downstream cascade, unlike the final
    holdout export.
    """
    candidates = list(dict.fromkeys(candidate_features))
    metric_rows: list[dict[str, Any]] = []
    importance_rows: list[dict[str, Any]] = []
    prediction_frames: list[pd.DataFrame] = []
    anchor_prediction_frames: list[pd.DataFrame] = []
    for train_idx, val_idx, fold_meta in folds:
        fold_train = train.iloc[train_idx]
        validation = train.iloc[val_idx]
        # Reserve the latest historical block for fold-local calibration.  It
        # is strictly before validation and prevents the exported V6 trend OOF
        # probabilities from being calibrated on the same rows used to fit
        # the base classifiers.
        fold_dates = np.array(sorted(fold_train["time"].unique()))
        calibration_start = max(
            1,
            len(fold_dates) - max(int(cfg.ablation_calibration_sessions), 1),
        )
        if calibration_start >= len(fold_dates):
            model_train = fold_train
            calibration = pd.DataFrame()
        else:
            calibration_start_date = pd.Timestamp(fold_dates[calibration_start])
            model_train = fold_train.loc[fold_train["time"] < calibration_start_date]
            calibration = fold_train.loc[fold_train["time"] >= calibration_start_date]
        calibration_ready = (
            len(model_train) > 0
            and len(calibration) > 0
            and model_train["wave_entry"].nunique() >= 2
            and calibration["wave_entry"].nunique() >= 2
        )
        if not calibration_ready:
            model_train = fold_train
            calibration = pd.DataFrame()
        # Fit preprocessing on the classifier-training slice only.  Including
        # the later calibration block here would leak its distribution into
        # the fold-local base models.
        fold_processor = fit_feature_processor(model_train, cfg, candidates)
        X_train = transform_features(model_train, fold_processor)
        X_validation = transform_features(validation, fold_processor)
        X_calibration = (
            transform_features(calibration, fold_processor)
            if calibration_ready else None
        )
        anchor_validation = None
        if anchor_frame is not None:
            anchor_validation = anchor_frame.loc[
                (anchor_frame["time"] >= pd.Timestamp(fold_meta["validation_start"]))
                & (anchor_frame["time"] <= pd.Timestamp(fold_meta["validation_end"]))
            ].copy()
        anchor_model_probabilities: dict[str, np.ndarray] = {}
        fold_predictions = validation[["time", "ticker", "wave_entry"]].reset_index(
            drop=True
        ).rename(columns={"time": "date", "ticker": "symbol", "wave_entry": "y_entry"})
        fold_predictions["fold_id"] = str(fold_meta["fold"])
        fold_predictions["sample_weight"] = event_uniqueness_weights(validation)
        calibration_probabilities: dict[str, np.ndarray] = {}
        for model_name in MODEL_NAMES:
            model = make_classifier(
                model_name, best_params[model_name], cfg.random_seed, cfg.compute_device
            )
            model.fit(
                X_train,
                model_train["wave_entry"].to_numpy(int),
                sample_weight=balanced_event_weights(model_train),
            )
            raw_validation = model.predict_proba(X_validation)[:, 1]
            probability = raw_validation
            if calibration_ready:
                raw_calibration = model.predict_proba(X_calibration)[:, 1]
                calibrator = fit_platt_calibrator(
                    raw_calibration,
                    calibration["wave_entry"].to_numpy(int),
                    cfg.random_seed,
                    date_balanced_weights(calibration),
                )
                probability = apply_platt(calibrator, raw_validation)
                calibration_probabilities[model_name] = apply_platt(
                    calibrator, raw_calibration
                )
            if anchor_validation is not None and not anchor_validation.empty:
                raw_anchor = model.predict_proba(
                    transform_features(anchor_validation, fold_processor)
                )[:, 1]
                anchor_model_probabilities[model_name] = (
                    apply_platt(calibrator, raw_anchor)
                    if calibration_ready
                    else raw_anchor
                )
            fold_predictions[f"p_{model_name}"] = probability
            metrics = classification_metrics(
                validation, probability, threshold=0.5, top_k=cfg.top_k_per_day
            )
            metric_rows.append({
                "model": model_name,
                "fold": fold_meta["fold"],
                "validation_start": fold_meta["validation_start"],
                "validation_end": fold_meta["validation_end"],
                "selected_features": len(fold_processor["features"]),
                "pr_lift": metrics["pr_auc"] / max(metrics["positive_rate"], EPS),
                **{key: value for key, value in metrics.items() if key != "confusion_matrix"},
            })

            raw_importance = np.asarray(model.feature_importances_, dtype=float)
            normalised = raw_importance / max(float(raw_importance.sum()), EPS)
            importance_map = dict(zip(fold_processor["features"], normalised))
            for feature in candidates:
                importance_rows.append({
                    "model": model_name,
                    "fold": fold_meta["fold"],
                    "feature": feature,
                    "selected": feature in importance_map,
                    "importance": float(importance_map.get(feature, 0.0)),
                })

        # Learn the candidate-ranking mixture using only the historical
        # calibration block.  This avoids both fixed stale weights and using
        # the validation OOF rows to select their own ensemble.
        if calibration_ready:
            calibration_matrix = np.column_stack([
                calibration_probabilities[name] for name in MODEL_NAMES
            ])
            ensemble_weights = learn_ensemble_weights(
                calibration_matrix,
                calibration,
                np.ones(len(MODEL_NAMES), dtype=bool),
                cfg,
            )
        else:
            ensemble_weights = np.full(
                len(MODEL_NAMES), 1.0 / len(MODEL_NAMES), dtype=float
            )
        validation_matrix = fold_predictions[
            [f"p_{name}" for name in MODEL_NAMES]
        ].to_numpy(float)
        fold_predictions["p_v6_trend"] = validation_matrix @ ensemble_weights
        # Backward-compatible alias for artifacts produced before V6 was
        # separated semantically from the fixed-horizon H20 onset head.
        fold_predictions["p_surge"] = fold_predictions["p_v6_trend"]
        for model_name, weight in zip(MODEL_NAMES, ensemble_weights):
            fold_predictions[f"ensemble_weight_{model_name}"] = float(weight)
        fold_predictions["p_v6_trend_is_calibrated"] = bool(calibration_ready)
        fold_predictions["p_surge_is_calibrated"] = bool(calibration_ready)
        prediction_frames.append(fold_predictions)
        if anchor_validation is not None and anchor_model_probabilities:
            anchor_predictions = anchor_validation[["time", "ticker"]].rename(
                columns={"time": "date", "ticker": "symbol"}
            ).reset_index(drop=True)
            for model_name in MODEL_NAMES:
                anchor_predictions[f"p_{model_name}"] = anchor_model_probabilities[model_name]
            anchor_matrix = anchor_predictions[[f"p_{name}" for name in MODEL_NAMES]].to_numpy(float)
            anchor_predictions["p_v6_trend"] = anchor_matrix @ ensemble_weights
            anchor_predictions["p_surge"] = anchor_predictions["p_v6_trend"]
            anchor_predictions["fold_id"] = str(fold_meta["fold"])
            anchor_predictions["p_v6_trend_is_calibrated"] = bool(calibration_ready)
            anchor_predictions["p_surge_is_calibrated"] = bool(calibration_ready)
            anchor_prediction_frames.append(anchor_predictions)

    metrics_table_cv = pd.DataFrame(metric_rows)
    importance_long = pd.DataFrame(importance_rows)
    stability = importance_long.groupby(["model", "feature"], observed=True).agg(
        folds=("fold", "nunique"),
        selection_rate=("selected", "mean"),
        importance_mean=("importance", "mean"),
        importance_std=("importance", lambda values: float(np.std(values, ddof=0))),
    ).reset_index()
    stability["importance_cv"] = stability["importance_std"] / (
        stability["importance_mean"] + EPS
    )
    stability = stability.sort_values(
        ["model", "importance_mean"], ascending=[True, False]
    ).reset_index(drop=True)
    if prediction_output is not None:
        if not prediction_frames:
            raise RuntimeError("No walk-forward predictions were generated")
        predictions = pd.concat(prediction_frames, ignore_index=True)
        prediction_output.parent.mkdir(parents=True, exist_ok=True)
        predictions.to_parquet(prediction_output, index=False)
    if anchor_prediction_output is not None:
        if not anchor_prediction_frames:
            raise RuntimeError("No anchor-population V6 predictions were generated")
        anchor_prediction_output.parent.mkdir(parents=True, exist_ok=True)
        pd.concat(anchor_prediction_frames, ignore_index=True).sort_values(
            ["date", "symbol"], kind="stable"
        ).to_parquet(anchor_prediction_output, index=False)
    return metrics_table_cv, stability


def run_feature_group_ablation(
    train: pd.DataFrame,
    folds: list[tuple[np.ndarray, np.ndarray, dict[str, str]]],
    cfg: Config,
) -> tuple[list[str], pd.DataFrame]:
    """Select a compact feature experiment using purged TRAIN folds only.

    A fixed conservative XGBoost configuration is used so the comparison tests
    feature information rather than giving every group a separate hyperparameter
    search budget.  Hyperparameter tuning happens only after the winning group
    is locked.
    """
    fixed_params = {
        "n_estimators": 300,
        "max_depth": 4,
        "learning_rate": 0.04,
        "min_child_weight": 8.0,
        "subsample": 0.80,
        "colsample_bytree": 0.80,
        "reg_alpha": 0.05,
        "reg_lambda": 2.0,
        "gamma": 0.10,
    }
    rows: list[dict[str, Any]] = []
    experiment_scores: dict[str, float] = {}
    for experiment, candidates in FEATURE_EXPERIMENTS.items():
        fold_metrics: list[dict[str, Any]] = []
        feature_counts: list[int] = []
        failure: str | None = None
        for train_idx, val_idx, fold_meta in folds:
            fold_train = train.iloc[train_idx]
            validation = train.iloc[val_idx]
            try:
                core_train, nested_calibration = nested_calibration_split(fold_train, cfg)

                fold_processor = fit_feature_processor(core_train, cfg, candidates)
                model = make_classifier("xgb", fixed_params, cfg.random_seed, cfg.compute_device)
                model.fit(
                    transform_features(core_train, fold_processor),
                    core_train["wave_entry"].to_numpy(int),
                    sample_weight=balanced_event_weights(core_train),
                )
                nested_raw = model.predict_proba(
                    transform_features(nested_calibration, fold_processor)
                )[:, 1]
                nested_weight = date_balanced_weights(nested_calibration)
                calibrator = fit_platt_calibrator(
                    nested_raw,
                    nested_calibration["wave_entry"].to_numpy(int),
                    cfg.random_seed,
                    nested_weight,
                )
                threshold, _ = select_threshold(
                    nested_calibration["wave_entry"].to_numpy(int),
                    apply_platt(calibrator, nested_raw),
                    nested_weight,
                )
                probability = apply_platt(calibrator, model.predict_proba(
                    transform_features(validation, fold_processor)
                )[:, 1])
                metrics = classification_metrics(
                    validation,
                    probability,
                    threshold=threshold,
                    top_k=cfg.top_k_per_day,
                )
                _, backtest_summary = top_k_outcome_backtest(validation, probability, cfg)
                if not backtest_summary.empty:
                    all_regimes = backtest_summary.loc[
                        backtest_summary["market_regime"].eq("ALL")
                    ].iloc[0]
                    for output_name in (
                        "hit_50_6m", "hit_100_6m", "hit_50_1y", "hit_100_1y",
                        "lift_50_6m", "lift_100_6m", "lift_50_1y", "lift_100_1y",
                    ):
                        metrics[f"backtest_{output_name}"] = float(all_regimes[output_name])
                metrics["fold"] = fold_meta["fold"]
                fold_metrics.append(metrics)
                feature_counts.append(len(fold_processor["features"]))
            except Exception as exc:
                failure = f"{type(exc).__name__}: {exc}"
                break

        if not fold_metrics or failure:
            row = {
                "experiment": experiment,
                "candidate_features": len(candidates),
                "folds": len(fold_metrics),
                "status": "failed",
                "error": failure or "no valid fold metrics",
                "selection_score": -np.inf,
            }
            rows.append(row)
            experiment_scores[experiment] = -np.inf
            continue

        table = pd.DataFrame(fold_metrics)
        pr_lift = table["pr_auc"] / table["positive_rate"].clip(lower=EPS)
        ranking_lift = table["lift_at_k"].clip(lower=EPS)
        fold_score = (
            0.60 * np.log(pr_lift.clip(lower=EPS)) +
            0.30 * np.log(ranking_lift) -
            0.10 * table["ece_10_bins"].clip(lower=0.0)
        )
        selection_score = float(fold_score.mean() - 0.20 * fold_score.std(ddof=0))
        experiment_scores[experiment] = selection_score
        rows.append({
            "experiment": experiment,
            "candidate_features": len(candidates),
            "selected_features_mean": float(np.mean(feature_counts)),
            "folds": len(fold_metrics),
            "status": "ok",
            "pr_auc_mean": float(table["pr_auc"].mean()),
            "pr_auc_std": float(table["pr_auc"].std(ddof=0)),
            "roc_auc_mean": float(table["roc_auc"].mean()),
            "precision_mean": float(table["precision"].mean()),
            "recall_mean": float(table["recall"].mean()),
            "f1_mean": float(table["f1"].mean()),
            "mcc_mean": float(table["mcc"].mean()),
            "brier_mean": float(table["brier"].mean()),
            "precision_at_k_mean": float(table["precision_at_k"].mean()),
            "recall_at_k_mean": float(table["recall_at_k"].mean()),
            "lift_at_k_mean": float(table["lift_at_k"].mean()),
            "date_relevance_base_rate_mean": float(table["positive_rate"].mean()),
            **{
                f"{column}_mean": float(table[column].mean())
                for column in table.columns if column.startswith("backtest_")
            },
            "selection_score": selection_score,
            "threshold_policy": "nested_purged_date_balanced_platt",
        })

    best_experiment = max(experiment_scores, key=experiment_scores.get)
    if not np.isfinite(experiment_scores[best_experiment]):
        failures = pd.DataFrame(rows)
        details = failures[["experiment", "error"]].to_dict(orient="records")
        raise RuntimeError(
            "Every feature-group ablation experiment failed: "
            f"{details}"
        )
    result = pd.DataFrame(rows)
    result["selected"] = result["experiment"].eq(best_experiment)
    return list(dict.fromkeys(FEATURE_EXPERIMENTS[best_experiment])), result


def raw_probability_matrix(models: dict[str, Any], frame: pd.DataFrame, processor: dict[str, Any]) -> np.ndarray:
    X = transform_features(frame, processor)
    return np.column_stack([models[name].predict_proba(X)[:, 1] for name in MODEL_NAMES])


def fit_platt_calibrator(
    raw_probability: np.ndarray,
    y: np.ndarray,
    seed: int,
    sample_weight: np.ndarray | None = None,
) -> LogisticRegression:
    raw = np.clip(raw_probability, 1e-6, 1 - 1e-6)
    logit = np.log(raw / (1 - raw)).reshape(-1, 1)
    calibrator = LogisticRegression(C=1.0, solver="lbfgs", random_state=seed)
    calibrator.fit(logit, y, sample_weight=sample_weight)
    return calibrator


def apply_platt(calibrator: LogisticRegression, raw_probability: np.ndarray) -> np.ndarray:
    raw = np.clip(raw_probability, 1e-6, 1 - 1e-6)
    logit = np.log(raw / (1 - raw)).reshape(-1, 1)
    return calibrator.predict_proba(logit)[:, 1]


def fit_individual_calibrators(
    cal_matrix_raw: np.ndarray,
    y: np.ndarray,
    seed: int,
    sample_weight: np.ndarray | None = None,
) -> dict[str, LogisticRegression]:
    return {
        name: fit_platt_calibrator(cal_matrix_raw[:, pos], y, seed, sample_weight)
        for pos, name in enumerate(MODEL_NAMES)
    }


def apply_individual_calibrators(
    raw_matrix: np.ndarray,
    calibrators: dict[str, LogisticRegression],
) -> np.ndarray:
    return np.column_stack([
        apply_platt(calibrators[name], raw_matrix[:, pos])
        for pos, name in enumerate(MODEL_NAMES)
    ])


def select_threshold(
    y: np.ndarray,
    probability: np.ndarray,
    sample_weight: np.ndarray | None = None,
) -> tuple[float, float]:
    candidates = np.unique(np.quantile(probability, np.linspace(0.02, 0.98, 97)))
    best_threshold, best_f1 = 0.5, -1.0
    for threshold in candidates:
        score = f1_score(
            y,
            probability >= threshold,
            sample_weight=sample_weight,
            zero_division=0,
        )
        if score > best_f1:
            best_threshold, best_f1 = float(threshold), float(score)
    return best_threshold, best_f1


def learn_ensemble_weights(
    calibrated_matrix: np.ndarray,
    frame: pd.DataFrame,
    active_mask: np.ndarray,
    cfg: Config,
) -> np.ndarray:
    y = frame["wave_entry"].to_numpy(int)
    sample_weight = date_balanced_weights(frame)
    active_indices = np.flatnonzero(active_mask)
    if active_indices.size == 0:
        active_indices = np.array([int(np.argmax([
            average_precision_score(
                y, calibrated_matrix[:, i], sample_weight=sample_weight
            ) for i in range(calibrated_matrix.shape[1])
        ]))])
    active = calibrated_matrix[:, active_indices]

    if active.shape[1] == 1:
        candidates = [np.ones(1, dtype=float)]
    else:
        step = 0.05
        units = int(round(1.0 / step))
        candidates = []
        if active.shape[1] == 2:
            for first in range(units + 1):
                candidate = np.array([first, units - first], dtype=float) / units
                if candidate.max() <= cfg.max_ensemble_weight + EPS:
                    candidates.append(candidate)
        else:
            for first in range(units + 1):
                for second in range(units - first + 1):
                    third = units - first - second
                    candidate = np.array([first, second, third], dtype=float) / units
                    if candidate.max() <= cfg.max_ensemble_weight + EPS:
                        candidates.append(candidate)
        if not candidates:
            candidates = [np.full(active.shape[1], 1.0 / active.shape[1])]

    base_rate = float(np.average(y, weights=sample_weight))
    baseline_brier = max(base_rate * (1.0 - base_rate), EPS)
    def candidate_score(candidate: np.ndarray) -> float:
        probability = active @ candidate
        pr_lift = average_precision_score(
            y, probability, sample_weight=sample_weight
        ) / max(base_rate, EPS)
        ranking = precision_at_k_by_date(
            frame, probability, cfg.top_k_per_day, sample_weight
        )
        top_lift = ranking["lift_at_k"]
        brier_ratio = brier_score_loss(
            y, probability, sample_weight=sample_weight
        ) / baseline_brier
        return float(
            0.60 * math.log(max(pr_lift, EPS)) +
            0.30 * math.log(max(top_lift, EPS)) -
            0.10 * brier_ratio
        )

    best_single_weights = np.eye(active.shape[1], dtype=float)
    single_scores = [candidate_score(candidate) for candidate in best_single_weights]
    best_single_pos = int(np.argmax(single_scores))
    best_single_score = float(single_scores[best_single_pos])

    best_score = -np.inf
    active_weights = candidates[0]
    for candidate in candidates:
        score = candidate_score(candidate)
        if score > best_score:
            best_score = score
            active_weights = candidate
    # Do not call a mixture an ensemble unless it adds measurable calibration /
    # ranking value over the best admitted single model. Weak models get zero.
    if best_score < best_single_score + cfg.min_ensemble_score_gain:
        active_weights = best_single_weights[best_single_pos]
    full = np.zeros(calibrated_matrix.shape[1], dtype=float)
    full[active_indices] = active_weights
    return full


# ---------------------------------------------------------------------------
# Metrics and ranking
# ---------------------------------------------------------------------------

def expected_calibration_error(
    y: np.ndarray,
    probability: np.ndarray,
    sample_weight: np.ndarray | None = None,
    bins: int = 10,
) -> float:
    weights = np.ones(len(y), dtype=float) if sample_weight is None else np.asarray(sample_weight, dtype=float)
    total_weight = max(float(weights.sum()), EPS)
    edges = np.linspace(0, 1, bins + 1)
    ece = 0.0
    for left, right in zip(edges[:-1], edges[1:]):
        mask = (probability >= left) & (probability < right if right < 1 else probability <= right)
        if mask.any():
            bin_weight = float(weights[mask].sum())
            observed = float(np.average(y[mask], weights=weights[mask]))
            predicted = float(np.average(probability[mask], weights=weights[mask]))
            ece += (bin_weight / total_weight) * abs(observed - predicted)
    return float(ece)


def precision_at_k_by_date(
    frame: pd.DataFrame,
    probability: np.ndarray,
    k: int,
    sample_weight: np.ndarray | None = None,
) -> dict[str, float]:
    scored = frame[["time", "wave_entry"]].copy()
    scored["probability"] = probability
    scored["sample_weight"] = (
        np.ones(len(scored), dtype=float) if sample_weight is None else sample_weight
    )
    daily_rows: list[dict[str, float]] = []
    for _, group in scored.groupby("time", observed=True, sort=True):
        top = group.nlargest(min(k, len(group)), "probability")
        raw_base = float(group["wave_entry"].mean())
        raw_precision = float(top["wave_entry"].mean())
        raw_recall = float(top["wave_entry"].sum() / max(group["wave_entry"].sum(), EPS))
        weighted_base = float(np.average(group["wave_entry"], weights=group["sample_weight"]))
        weighted_precision = float(np.average(top["wave_entry"], weights=top["sample_weight"]))
        positive_weight = float((group["wave_entry"] * group["sample_weight"]).sum())
        captured_weight = float((top["wave_entry"] * top["sample_weight"]).sum())
        daily_rows.append({
            "raw_base": raw_base,
            "raw_precision": raw_precision,
            "raw_recall": raw_recall,
            "raw_lift": raw_precision / max(raw_base, EPS),
            "weighted_base": weighted_base,
            "weighted_precision": weighted_precision,
            "weighted_recall": captured_weight / max(positive_weight, EPS),
            "weighted_lift": weighted_precision / max(weighted_base, EPS),
        })
    if not daily_rows:
        return {
            "precision_at_k": float("nan"), "recall_at_k": float("nan"),
            "lift_at_k": float("nan"), "weighted_precision_at_k": float("nan"),
            "weighted_recall_at_k": float("nan"),
            "weighted_lift_at_k": float("nan"), "days_evaluated": 0,
        }
    daily = pd.DataFrame(daily_rows)
    return {
        # Primary Top-K metrics are raw macro averages across rebalance dates.
        # The weighted variants reflect whichever audit weights were supplied.
        "precision_at_k": float(daily["raw_precision"].mean()),
        "recall_at_k": float(daily["raw_recall"].mean()),
        "lift_at_k": float(daily["raw_lift"].mean()),
        "weighted_precision_at_k": float(daily["weighted_precision"].mean()),
        "weighted_recall_at_k": float(daily["weighted_recall"].mean()),
        "weighted_lift_at_k": float(daily["weighted_lift"].mean()),
        "days_evaluated": int(len(daily)),
    }


def classification_metrics(
    frame: pd.DataFrame,
    probability: np.ndarray,
    threshold: float,
    top_k: int,
    sample_weight: np.ndarray | None = None,
) -> dict[str, Any]:
    y = frame["wave_entry"].to_numpy(int)
    weights = date_balanced_weights(frame) if sample_weight is None else sample_weight
    event_weights = event_uniqueness_weights(frame)
    prediction = (probability >= threshold).astype(int)
    result: dict[str, Any] = {
        "samples": int(len(y)),
        "raw_positive_rate": float(y.mean()),
        "positive_rate": float(np.average(y, weights=weights)),
        "positives": int(y.sum()),
        "evaluation_weight_sum": float(np.sum(weights)),
        "pr_auc": float(average_precision_score(y, probability, sample_weight=weights)),
        "roc_auc": float(roc_auc_score(y, probability, sample_weight=weights)),
        "brier": float(brier_score_loss(y, probability, sample_weight=weights)),
        "log_loss": float(log_loss(y, np.clip(probability, 1e-6, 1 - 1e-6), sample_weight=weights)),
        "ece_10_bins": expected_calibration_error(y, probability, weights),
        "threshold": float(threshold),
        "precision": float(precision_score(y, prediction, sample_weight=weights, zero_division=0)),
        "recall": float(recall_score(y, prediction, sample_weight=weights, zero_division=0)),
        "f1": float(f1_score(y, prediction, sample_weight=weights, zero_division=0)),
        "mcc": float(matthews_corrcoef(y, prediction, sample_weight=weights)),
        "confusion_matrix": confusion_matrix(y, prediction, sample_weight=weights).tolist(),
        "event_weighted_positive_rate": float(np.average(y, weights=event_weights)),
        "event_weighted_pr_auc": float(average_precision_score(
            y, probability, sample_weight=event_weights
        )),
        "event_weighted_roc_auc": float(roc_auc_score(
            y, probability, sample_weight=event_weights
        )),
        "event_weighted_brier": float(brier_score_loss(
            y, probability, sample_weight=event_weights
        )),
    }
    result.update(precision_at_k_by_date(frame, probability, top_k, weights))
    return result


def metrics_table(
    frame: pd.DataFrame,
    probability_by_name: dict[str, np.ndarray],
    thresholds: dict[str, float],
    top_k: int,
) -> pd.DataFrame:
    rows = []
    for name, probability in probability_by_name.items():
        metrics = classification_metrics(frame, probability, thresholds[name], top_k)
        rows.append({"model": name, **{k: v for k, v in metrics.items() if k != "confusion_matrix"}})
    return pd.DataFrame(rows).sort_values("pr_auc", ascending=False).reset_index(drop=True)


def calibration_reliability_table(
    frame: pd.DataFrame,
    probability_by_name: dict[str, np.ndarray],
    bins: int = 10,
) -> pd.DataFrame:
    """Return raw and event-weighted reliability bins for every model."""
    y = frame["wave_entry"].to_numpy(int)
    event_weights = event_uniqueness_weights(frame)
    date_weights = date_balanced_weights(frame)
    rows: list[dict[str, Any]] = []
    edges = np.linspace(0.0, 1.0, bins + 1)
    for model_name, probability in probability_by_name.items():
        probability = np.asarray(probability, dtype=float)
        for bin_number, (left, right) in enumerate(zip(edges[:-1], edges[1:]), 1):
            mask = (probability >= left) & (
                probability < right if right < 1.0 else probability <= right
            )
            if not mask.any():
                continue
            rows.append({
                "model": model_name,
                "bin": bin_number,
                "probability_left": left,
                "probability_right": right,
                "rows": int(mask.sum()),
                "predicted_mean": float(probability[mask].mean()),
                "observed_rate": float(y[mask].mean()),
                "date_weighted_predicted_mean": float(np.average(
                    probability[mask], weights=date_weights[mask]
                )),
                "date_weighted_observed_rate": float(np.average(
                    y[mask], weights=date_weights[mask]
                )),
                "event_weighted_predicted_mean": float(np.average(
                    probability[mask], weights=event_weights[mask]
                )),
                "event_weighted_observed_rate": float(np.average(
                    y[mask], weights=event_weights[mask]
                )),
            })
    return pd.DataFrame(rows)


def top_k_outcome_backtest(
    frame: pd.DataFrame,
    probability: np.ndarray,
    cfg: Config,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Audit Top-50 realised outcomes at non-overlapping monthly scan cohorts.

    This is a ranking audit, not a portfolio-PnL simulator: it ignores position
    overlap, sizing, limit-up execution and taxes beyond the target's simple
    round-trip cost. It directly answers how often selected names later touched
    +50%/+100% within roughly six months and one year.
    """
    scored = frame.copy()
    scored["probability"] = np.asarray(probability, dtype=float)
    dates = np.array(sorted(scored["time"].dropna().unique()))
    date_step = max(
        int(round(cfg.backtest_rebalance_sessions / effective_sample_stride_sessions(cfg))),
        1,
    )
    cohort_dates = set(pd.to_datetime(dates[::date_step]))
    cohort_rows: list[dict[str, Any]] = []
    for date, universe in scored.groupby("time", observed=True, sort=True):
        if pd.Timestamp(date) not in cohort_dates:
            continue
        selected = universe.nlargest(min(cfg.top_k_per_day, len(universe)), "probability")
        market_above = float(universe["market_price_to_ma200"].dropna().median())
        market_momentum = float(universe["market_ret_60"].dropna().median())
        if market_above > 0 and market_momentum > 0:
            regime = "BULL"
        elif market_above < 0 and market_momentum < 0:
            regime = "BEAR"
        else:
            regime = "MIXED"

        row: dict[str, Any] = {
            "time": pd.Timestamp(date),
            "market_regime": regime,
            "universe_size": int(len(universe)),
            "selected": int(len(selected)),
            "mean_probability": float(selected["probability"].mean()),
        }
        for horizon_name, return_column in (
            ("6m", "future_max_return_126"),
            ("1y", "future_max_return_252"),
        ):
            for threshold_name, threshold in (("50", 0.50), ("100", 1.00)):
                selected_outcomes = pd.to_numeric(
                    selected[return_column], errors="coerce"
                ).dropna()
                universe_outcomes = pd.to_numeric(
                    universe[return_column], errors="coerce"
                ).dropna()
                selected_rate = (
                    float(selected_outcomes.ge(threshold).mean())
                    if not selected_outcomes.empty else np.nan
                )
                universe_rate = (
                    float(universe_outcomes.ge(threshold).mean())
                    if not universe_outcomes.empty else np.nan
                )
                row[f"hit_{threshold_name}_{horizon_name}"] = selected_rate
                row[f"universe_hit_{threshold_name}_{horizon_name}"] = universe_rate
                row[f"lift_{threshold_name}_{horizon_name}"] = (
                    selected_rate / max(universe_rate, EPS)
                    if np.isfinite(selected_rate) and np.isfinite(universe_rate)
                    else np.nan
                )
        row["mean_terminal_return_6m"] = float(selected["future_terminal_return_126"].mean())
        row["median_terminal_return_6m"] = float(selected["future_terminal_return_126"].median())
        row["mean_terminal_return_1y"] = float(selected["future_terminal_return_252"].mean())
        row["median_terminal_return_1y"] = float(selected["future_terminal_return_252"].median())
        cohort_rows.append(row)

    cohorts = pd.DataFrame(cohort_rows)
    if cohorts.empty:
        return cohorts, pd.DataFrame()
    numeric = [
        column for column in cohorts.columns
        if column not in {"time", "market_regime"}
    ]
    summaries: list[dict[str, Any]] = []
    for regime, group in [("ALL", cohorts), *list(cohorts.groupby("market_regime", observed=True))]:
        summary: dict[str, Any] = {
            "market_regime": regime,
            "cohorts": int(len(group)),
        }
        for column in numeric:
            summary[column] = float(group[column].mean())
        summaries.append(summary)
    return cohorts, pd.DataFrame(summaries)


def feature_importance_table(models: dict[str, Any], processor: dict[str, Any], weights: np.ndarray) -> pd.DataFrame:
    features = processor["features"]
    table = pd.DataFrame({"feature": features})
    combined = np.zeros(len(features), dtype=float)
    for pos, name in enumerate(MODEL_NAMES):
        importance = np.asarray(models[name].feature_importances_, dtype=float)
        if importance.size != len(features):
            raise RuntimeError(f"{name} returned {importance.size} importances for {len(features)} features")
        norm = importance / max(float(importance.sum()), EPS)
        table[f"importance_{name}"] = norm
        combined += weights[pos] * norm
    table["importance_ensemble"] = combined
    return table.sort_values("importance_ensemble", ascending=False).reset_index(drop=True)


def add_entry_quality(frame: pd.DataFrame) -> pd.DataFrame:
    """Add an interpretable timing score; this is deliberately not a probability.

    Wave probability answers whether a confirmed major wave may still be ahead.
    Entry quality answers whether the current technical location is reasonably
    early/actionable rather than already stretched.  Keeping the two quantities
    separate avoids hard-removing genuine leaders near a breakout/high.
    """
    out = frame.copy()

    def risk_above(column: str, safe: float, extreme: float) -> pd.Series:
        values = pd.to_numeric(out[column], errors="coerce")
        return ((values - safe) / max(extreme - safe, EPS)).clip(0, 1).fillna(0.5)

    extension_risk = (
        0.18 * risk_above("ret_20", 0.15, 0.35) +
        0.22 * risk_above("ret_60", 0.35, 0.80) +
        0.16 * risk_above("price_to_ma20", 0.10, 0.25) +
        0.16 * risk_above("price_to_ma50", 0.22, 0.50) +
        0.14 * risk_above("rsi10", 72.0, 90.0) +
        0.14 * risk_above("atr_extension_20", 3.0, 8.0)
    ).clip(0, 1)

    breakout = pd.to_numeric(out["breakout_55"], errors="coerce")
    # Highest near the old high or a modest breakout; falls when far below it or
    # already >15% above it.  Near-high alone is never an exclusion rule.
    breakout_setup = (1.0 - (breakout - 0.01).abs() / 0.18).clip(0, 1).fillna(0)
    contraction_parts = pd.concat([
        ((1.25 - pd.to_numeric(out["volatility_contraction_20_120"], errors="coerce")) / 0.65).clip(0, 1),
        ((1.20 - pd.to_numeric(out["atr_contraction_14_60"], errors="coerce")) / 0.50).clip(0, 1),
        ((1.20 - pd.to_numeric(out["range_contraction_20_120"], errors="coerce")) / 0.50).clip(0, 1),
    ], axis=1)
    contraction = contraction_parts.mean(axis=1).fillna(0)
    base_stability = pd.to_numeric(out["base_stability_120"], errors="coerce").clip(0, 1).fillna(0)
    volume_setup = (
        0.55 * ((pd.to_numeric(out["volume_ratio_20"], errors="coerce") - 0.75) / 1.50).clip(0, 1) +
        0.45 * pd.to_numeric(out["volume_persistence_20"], errors="coerce").clip(0, 1)
    ).fillna(0)
    rs_percentile = pd.to_numeric(out["rs_rank_market_60"], errors="coerce").fillna(0.5)
    liquidity_setup = pd.to_numeric(out["liquidity_percentile"], errors="coerce").fillna(0.0)
    setup_strength = (
        0.20 * breakout_setup +
        0.20 * contraction +
        0.15 * base_stability +
        0.15 * volume_setup +
        0.25 * rs_percentile +
        0.05 * liquidity_setup
    ).clip(0, 1)

    entry_quality = 100.0 * (1.0 - extension_risk) * (0.55 + 0.45 * setup_strength)
    out["overextension_risk"] = extension_risk
    out["setup_strength"] = setup_strength
    out["entry_quality"] = entry_quality.clip(0, 100)

    conditions = [
        extension_risk.ge(0.60),
        breakout.between(0.0, 0.10) & out["volume_ratio_20"].ge(1.10),
        breakout.between(-0.15, 0.02) & contraction.ge(0.55) &
        base_stability.ge(0.60) & rs_percentile.ge(0.55),
        out["price_to_ma50"].gt(0) & out["stock_rs_market_60"].gt(0),
    ]
    out["setup_status"] = np.select(
        conditions,
        ["OVEREXTENDED", "BREAKOUT", "EARLY_SETUP", "TRENDING"],
        default="WEAK_SETUP",
    )
    return out


def build_latest_ranking(
    latest: pd.DataFrame,
    calibrated_matrix: np.ndarray,
    ensemble_probability: np.ndarray,
    ensemble_weights: np.ndarray,
    cfg: Config,
) -> pd.DataFrame:
    columns = [
        "time", "ticker", "industry", "close", "volume", "market_cap",
        "median_value_traded_60", "avg_value_traded_20", "avg_value_traded_60",
        "avg_volume_20", "avg_volume_60",
        "observed_ratio_60", "zero_volume_ratio_60",
        "abnormal_volume_ratio_60", "volatility_20", "volatility_60", "max_drawdown_120",
        "ret_20", "ret_60", "ret_120", "trend_r2_60",
        "price_to_ma20", "price_to_ma50", "price_to_ma200", "ma50_to_ma200", "slope_60",
        "distance_from_high_252", "distance_from_prior_high_252", "atr_extension_20",
        "base_contraction", "volatility_contraction_20_120", "atr_contraction_14_60",
        "range_contraction_20_120", "base_stability_120", "base_range_60",
        "base_range_120", "breakout_55",
        "rsi10", "stock_rs_market_60", "rs_rank_market_60", "volume_ratio_20",
        "volume_persistence_20", "volume_ratio_short_long", "up_down_volume_ratio_60",
        "liquidity_percentile", "sector_rank_60", "leader_score",
    ]
    ranked = latest[[c for c in columns if c in latest.columns]].copy()
    for pos, name in enumerate(MODEL_NAMES):
        ranked[f"p_{name}"] = calibrated_matrix[:, pos]
        ranked[f"p_{name}_pct"] = calibrated_matrix[:, pos] * 100.0
    for name in CANONICAL_MODEL_NAMES:
        if f"p_{name}" not in ranked:
            ranked[f"p_{name}"] = np.nan
            ranked[f"p_{name}_pct"] = np.nan
    ranked["p_ensemble"] = ensemble_probability
    ranked["p_ensemble_pct"] = ensemble_probability * 100.0
    ranked["model_probability_std"] = calibrated_matrix.std(axis=1)
    ranked["model_agreement"] = 1.0 - np.clip(ranked["model_probability_std"] / 0.25, 0, 1)
    active_weighted_mean = calibrated_matrix @ ensemble_weights
    weighted_variance = np.sum(
        ensemble_weights.reshape(1, -1) *
        (calibrated_matrix - active_weighted_mean.reshape(-1, 1)) ** 2,
        axis=1,
    )
    ranked["active_model_agreement"] = 1.0 - np.clip(np.sqrt(weighted_variance) / 0.25, 0, 1)
    ranked = add_entry_quality(ranked)
    ranked["actionable_score"] = ranked["p_ensemble"] * (
        0.35 + 0.65 * ranked["entry_quality"] / 100.0
    )
    ranked = add_portfolio_quality_scores(ranked)
    ranked = ranked.sort_values(["p_ensemble", "model_agreement"], ascending=[False, False]).reset_index(drop=True)
    ranked["rank"] = np.arange(1, len(ranked) + 1)
    actionable_order = ranked["actionable_score"].rank(method="first", ascending=False).astype(int)
    ranked["actionable_rank"] = actionable_order
    return ranked.head(cfg.latest_top_n).copy()


def _json_dump(path: Path, payload: dict[str, Any]) -> None:
    def convert(value: Any):
        if isinstance(value, (np.integer,)):
            return int(value)
        if isinstance(value, (np.floating,)):
            return float(value)
        if isinstance(value, (pd.Timestamp, datetime)):
            return value.isoformat()
        if isinstance(value, Path):
            return str(value)
        raise TypeError(f"Cannot serialise {type(value).__name__}")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=convert), encoding="utf-8")


def rerank_existing_probabilities(
    probability_path: Path,
    reports_dir: Path,
    top_n: int,
) -> dict[str, Any]:
    """Apply the second-stage ranking without fitting or calibrating any model.

    This fast path is intentionally limited to an already exported latest
    probability universe.  It never changes the saved model bundle and never
    downloads market data.
    """
    if not probability_path.is_file():
        raise FileNotFoundError(f"Existing probability file not found: {probability_path}")
    existing = pd.read_csv(probability_path)
    required = {"ticker"}
    if not ({"p_ensemble", "p_ensemble_pct"} & set(existing.columns)):
        required.add("p_ensemble or p_ensemble_pct")
    missing_required = sorted(required - set(existing.columns))
    if missing_required:
        raise ValueError(
            "Existing probability file is missing required columns: "
            + ", ".join(missing_required)
        )
    if "p_ensemble_pct" not in existing:
        existing["p_ensemble_pct"] = pd.to_numeric(
            existing["p_ensemble"], errors="coerce"
        ) * 100.0
    if "p_ensemble" not in existing:
        existing["p_ensemble"] = pd.to_numeric(
            existing["p_ensemble_pct"], errors="coerce"
        ) / 100.0
    if "model_agreement" not in existing:
        existing["model_agreement"] = 0.5

    recommended_diagnostics = {
        "base_stability_120", "base_range_60", "base_range_120",
        "volatility_contraction_20_120", "atr_contraction_14_60",
        "range_contraction_20_120", "volume_ratio_20",
        "volume_ratio_short_long", "volume_persistence_20",
        "up_down_volume_ratio_60", "abnormal_volume_ratio_60",
        "price_to_ma20", "price_to_ma50", "price_to_ma200",
        "ma50_to_ma200", "slope_60", "stock_rs_market_60",
        "rs_rank_market_60", "sector_rank_60", "trend_r2_60",
        "ret_60", "ret_120",
    }
    missing_diagnostics = sorted(recommended_diagnostics - set(existing.columns))
    if missing_diagnostics:
        warnings.warn(
            "Fast rerank is using neutral values for diagnostics absent from the old export: "
            + ", ".join(missing_diagnostics),
            RuntimeWarning,
        )

    scored = add_portfolio_quality_scores(existing, PortfolioRankingConfig())
    before = scored.sort_values(
        ["p_ensemble_pct", "model_agreement"], ascending=[False, False]
    ).head(top_n)
    after = select_diversified_top_k(
        scored, k=top_n, config=PortfolioRankingConfig()
    )
    reports_dir.mkdir(parents=True, exist_ok=True)
    full_path = reports_dir / "latest_full_universe_accumulation_reranked.csv"
    top_path = reports_dir / "top50_portfolio_ranked.csv"
    scored.sort_values(
        ["final_score", "p_ensemble_pct"], ascending=[False, False]
    ).to_csv(full_path, index=False)
    after.to_csv(top_path, index=False)

    comparison = {
        "mode": "rerank_existing_probabilities_without_retraining",
        "source_probability_file": str(probability_path),
        "source_as_of_date": (
            str(pd.to_datetime(existing["time"], errors="coerce").max().date())
            if "time" in existing and pd.to_datetime(
                existing["time"], errors="coerce"
            ).notna().any()
            else None
        ),
        "missing_diagnostics_given_neutral_score": missing_diagnostics,
        "before_wave_probability_only": ranking_profile(before),
        "after_accumulation_risk_and_diversification": ranking_profile(after),
        "important_note": (
            "Model probabilities and calibration are unchanged. Re-run the full pipeline only "
            "when a complete historical holdout comparison or newly added pass-through "
            "diagnostics is required."
        ),
    }
    _json_dump(reports_dir / "portfolio_ranking_comparison.json", comparison)

    report_path = reports_dir / "evaluation_report.json"
    if report_path.is_file():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            report = {}
    else:
        report = {}
    report["latest_rerank_only"] = comparison
    report["top50_portfolio_path"] = str(top_path)
    _json_dump(report_path, report)

    print("\nTOP portfolio candidates from existing calibrated probabilities:")
    visible = [
        "portfolio_rank", "ticker", "wave_probability", "accumulation_score",
        "trend_quality_score", "liquidity_score", "pump_risk_score",
        "final_score", "setup_status",
    ]
    print(after[[column for column in visible if column in after]].to_string(index=False))
    print(f"\nSaved: {top_path}")
    print(f"Full reranked universe: {full_path}")
    return comparison


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def train_pipeline(
    cfg: Config,
    allow_stale_cache: bool = False,
    save_feature_store: bool = False,
    oof_only: bool = False,
    anchor_dataset_run: str | None = None,
    lock_feature_experiment: str | None = None,
    lock_ensemble_weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    models_dir, reports_dir = Path(cfg.models_dir), Path(cfg.reports_dir)
    if cfg.lead_time_half_life_sessions <= 0:
        raise ValueError("lead_time_half_life_sessions must be positive")
    if not (0 < cfg.min_late_positive_relevance <= 1):
        raise ValueError("min_late_positive_relevance must be in (0, 1]")

    print("\n[1/12] Building cleaned point-in-time panel + unbounded structural-event labels")
    panel, data_meta, ticker_quality = build_panel(cfg, allow_stale_cache=allow_stale_cache)
    models_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    ticker_quality.to_csv(reports_dir / "ticker_quality.csv", index=False)
    labelled, unlabelled = prepare_samples(panel, cfg)
    anchor_frame = None
    anchor_dependency = None
    if anchor_dataset_run is not None:
        anchor_run = Path(anchor_dataset_run).resolve()
        anchor_key_files = sorted(anchor_run.glob("splits/fold_*/validation_keys.parquet"))
        if not anchor_key_files:
            raise RuntimeError(
                f"Anchor dataset run must contain validation keys: {anchor_run}"
            )
        anchor_keys = pd.concat(
            (pd.read_parquet(path) for path in anchor_key_files), ignore_index=True
        ).rename(columns={"symbol": "ticker", "date": "time"})
        anchor_keys["time"] = pd.to_datetime(anchor_keys["time"], errors="raise")
        # Use the V6-built panel for features.  Continuation datasets share
        # logical signals but not necessarily V6's internal feature names
        # (e.g. momentum_60 versus ret_60).
        anchor_frame = panel.reset_index().merge(
            anchor_keys[["ticker", "time"]].drop_duplicates(),
            on=["ticker", "time"],
            how="inner",
            validate="one_to_one",
        )
        anchor_dependency = {
            "run": str(anchor_run),
            "rows": int(len(anchor_frame)),
            "dates": int(anchor_frame["time"].nunique()),
            "prediction_output": str((reports_dir / "anchor_oof_predictions.parquet").resolve()),
        }
    if labelled["ticker"].nunique() < cfg.min_model_symbols and not allow_stale_cache:
        raise RuntimeError(
            f"Only {labelled['ticker'].nunique()} symbols have labelled eligible samples; "
            f"need at least {cfg.min_model_symbols}."
        )
    data_meta.update({
        "labelled_samples": int(len(labelled)),
        "resolved_positive_rate": float(labelled["wave_entry"].mean()),
        "event_weighted_resolved_positive_rate": float(np.average(
            labelled["wave_entry"], weights=event_uniqueness_weights(labelled)
        )),
        "resolved_positives": int(labelled["wave_entry"].sum()),
        "right_censored_inference_rows": int(len(unlabelled)),
        "diagnostic_252_positive_rate": _safe_numeric_mean(labelled["wave_entry_252"]),
        "median_positive_lead_sessions": _safe_numeric_median(
            labelled.loc[labelled["wave_entry"].eq(1), "event_sessions"]
        ),
        "median_positive_relevance_weight": _safe_numeric_median(
            labelled.loc[labelled["wave_entry"].eq(1), "label_relevance_weight"]
        ),
        "future_waves_rejected_as_already_extended": int((
            labelled["event_return"].ge(cfg.strong_wave_return) &
            labelled["wave_entry"].eq(0)
        ).sum()),
        "target_resolution_counts": {
            str(key): int(value) for key, value in
            panel["target_resolution"].value_counts(dropna=False).items()
        },
    })

    quality_status = ticker_quality["status"].value_counts(dropna=False).to_dict()
    latest_eligible_count = (
        int(ticker_quality["latest_eligible"].astype("boolean").fillna(False).sum())
        if "latest_eligible" in ticker_quality.columns else 0
    )
    data_quality_summary = {
        "input_symbols": int(data_meta["freshness"]["total_symbols"]),
        "loaded_symbols": int(data_meta["loaded_symbols"]),
        "symbols_rejected_before_panel": int(
            ticker_quality["status"].ne("loaded").sum()
        ),
        "status_counts": {str(key): int(value) for key, value in quality_status.items()},
        "panel_rows": int(len(panel)),
        "eligible_rows": int(panel["eligible"].fillna(False).sum()),
        "labelled_rows_after_weekly_sampling": int(len(labelled)),
        "right_censored_eligible_rows": int(len(unlabelled)),
        "latest_eligible_symbols_in_quality_audit": latest_eligible_count,
        "hard_absolute_liquidity_filter": False,
        "liquidity_policy": (
            "strict trading-continuity/data-quality gates plus point-in-time relative "
            "liquidity features; absolute traded value is audit-only"
        ),
        "row_failure_counts_non_exclusive": {
            column.removeprefix("quality_").removesuffix("_ok"): int(
                (~panel[column].fillna(False)).sum()
            )
            for column in (
                "quality_observed_candle",
                "quality_history_ok",
                "quality_observed_60_ok",
                "quality_observed_120_ok",
                "quality_zero_volume_ok",
                "quality_corporate_action_ok",
                "quality_volume_anomaly_ok",
            )
        },
    }
    _json_dump(reports_dir / "data_quality_summary.json", data_quality_summary)

    label_audit = labelled.assign(
        year=labelled["time"].dt.year,
        event_weight=event_uniqueness_weights(labelled),
    )
    label_balance_rows: list[dict[str, Any]] = []
    for year, group in label_audit.groupby("year", observed=True, sort=True):
        positive_group = group.loc[group["wave_entry"].eq(1)]
        label_balance_rows.append({
            "year": int(year),
            "samples": len(group),
            "positives": int(group["wave_entry"].sum()),
            "raw_positive_rate": _safe_numeric_mean(group["wave_entry"]),
            "positive_rate_252": _safe_numeric_mean(group["wave_entry_252"]),
            "median_positive_lead_sessions": _safe_numeric_median(
                positive_group["event_sessions"]
            ),
            "median_positive_relevance_weight": _safe_numeric_median(
                positive_group["label_relevance_weight"]
            ),
            "event_weighted_positive_rate": float(
                np.average(group["wave_entry"], weights=group["event_weight"])
            ),
        })
    label_balance = pd.DataFrame(label_balance_rows)
    label_balance.to_csv(reports_dir / "label_balance_by_year.csv", index=False)

    if save_feature_store:
        store_cols = [
            "time", "ticker", "industry", "entry_time", "label_end_time", "eligible",
            "wave_entry", "wave_entry_252", "raw_confirmed_wave_252",
            "target_resolution", "pre_wave_state", "major_wave_confirmed",
            "structural_failure_confirmed",
            "event_sessions", "event_return", "label_relevance_weight",
            "future_max_return_126", "future_max_return_252",
            "future_terminal_return_126", "future_terminal_return_252", *CANDIDATE_FEATURES,
        ]
        joblib.dump(panel[store_cols], Path(cfg.data_dir) / "feature_store_wave_v6.joblib", compress=3)

    print("\n[2/12] Creating purged train/calibration/test splits")
    market_dates = np.array(sorted(panel["time"].dropna().unique()))
    train, calibration, test, boundaries = split_train_calibration_test(labelled, market_dates, cfg)
    folds = purged_walk_forward_folds(train, cfg)
    train_event_rate = float(np.average(
        train["wave_entry"], weights=event_uniqueness_weights(train)
    ))
    cal_event_rate = float(np.average(
        calibration["wave_entry"], weights=event_uniqueness_weights(calibration)
    ))
    test_event_rate = float(np.average(
        test["wave_entry"], weights=event_uniqueness_weights(test)
    ))
    print(
        f"Train={len(train):,} (raw={train['wave_entry'].mean():.2%}, event={train_event_rate:.2%}), "
        f"Cal={len(calibration):,} (raw={calibration['wave_entry'].mean():.2%}, event={cal_event_rate:.2%}), "
        f"Test={len(test):,} (raw={test['wave_entry'].mean():.2%}, event={test_event_rate:.2%})"
    )

    print("\n[3/12] Purged TRAIN-only feature-group ablation")
    winning_candidates, ablation = run_feature_group_ablation(train, folds, cfg)
    if lock_feature_experiment is not None:
        if lock_feature_experiment not in FEATURE_EXPERIMENTS:
            raise ValueError(
                f"Unknown locked feature experiment {lock_feature_experiment!r}; "
                f"choose one of {sorted(FEATURE_EXPERIMENTS)}"
            )
        winning_candidates = list(dict.fromkeys(FEATURE_EXPERIMENTS[lock_feature_experiment]))
        winning_experiment = lock_feature_experiment
        ablation["selected"] = ablation["experiment"].eq(lock_feature_experiment)
    else:
        winning_experiment = str(ablation.loc[ablation["selected"], "experiment"].iloc[0])
    ablation.to_csv(reports_dir / "feature_group_ablation.csv", index=False)
    print(f"Selected feature experiment: {winning_experiment}")

    print("\n[4/12] Train-only feature screening, de-correlation, clipping, imputation")
    processor = fit_feature_processor(train, cfg, winning_candidates)
    processor["quality_table"].to_csv(reports_dir / "feature_quality.csv", index=False)
    pd.DataFrame({"feature": processor["features"]}).to_csv(reports_dir / "selected_features.csv", index=False)
    print(
        f"Selected {len(processor['features'])}/{len(winning_candidates)} features "
        f"from {len(CANDIDATE_FEATURES)} total candidates"
    )

    liquidity_summary = train[VOLUME_REGIME_FEATURES].describe(
        percentiles=[0.01, 0.10, 0.50, 0.90, 0.99]
    ).T.reset_index(names="feature")
    liquidity_summary["missing_rate"] = [
        float(train[feature].isna().mean()) for feature in liquidity_summary["feature"]
    ]
    liquidity_summary.to_csv(reports_dir / "liquidity_feature_summary.csv", index=False)

    print("\n[5/12] Optuna tuning with fold-local preprocessing and PR/Lift objective")
    best_params: dict[str, dict[str, Any]] = {}
    tuning_summary: dict[str, Any] = {}
    for name in MODEL_NAMES:
        print(f"Tuning {name.upper()}...")
        best_params[name], tuning_summary[name] = tune_classifier(
            name, train, folds, winning_candidates, cfg
        )

    print("\n[6/12] Walk-forward model and feature-importance stability diagnostics")
    cv_model_metrics, importance_stability = walk_forward_model_diagnostics(
        train,
        folds,
        best_params,
        winning_candidates,
        cfg,
        prediction_output=reports_dir / "walk_forward_oof_predictions.parquet",
        anchor_frame=anchor_frame,
        anchor_prediction_output=(
            reports_dir / "anchor_oof_predictions.parquet"
            if anchor_frame is not None else None
        ),
    )
    cv_model_metrics.to_csv(reports_dir / "model_metrics_walk_forward.csv", index=False)
    importance_stability.to_csv(
        reports_dir / "feature_importance_stability_walk_forward.csv", index=False
    )
    cv_model_summary = cv_model_metrics.groupby("model", observed=True).agg(
        folds=("fold", "nunique"),
        pr_auc_mean=("pr_auc", "mean"),
        pr_auc_std=("pr_auc", lambda values: float(np.std(values, ddof=0))),
        pr_lift_mean=("pr_lift", "mean"),
        roc_auc_mean=("roc_auc", "mean"),
        precision_at_50_mean=("precision_at_k", "mean"),
        lift_at_50_mean=("lift_at_k", "mean"),
        brier_mean=("brier", "mean"),
    ).reset_index()
    cv_support = cv_model_metrics.assign(
        supports=lambda table: table["pr_lift"].ge(1.0) & table["lift_at_k"].ge(1.0)
    ).groupby("model", observed=True)["supports"].agg(["sum", "count"]).reset_index()
    cv_support["stable_signal"] = cv_support["sum"] >= np.ceil(cv_support["count"] / 2)
    cv_model_summary = cv_model_summary.merge(
        cv_support[["model", "sum", "stable_signal"]].rename(
            columns={"sum": "supporting_folds"}
        ),
        on="model",
        how="left",
    )
    cv_model_summary.to_csv(reports_dir / "model_metrics_walk_forward_summary.csv", index=False)

    if oof_only:
        report = {
            "status": "causal_oof_export_complete",
            "final_holdout_opened": False,
            "latest_inference_run": False,
            "config": asdict(cfg),
            "data": data_meta,
            "split_boundaries": boundaries,
            "walk_forward_folds": [meta for _, _, meta in folds],
            "selected_feature_experiment": winning_experiment,
            "selected_features": processor["features"],
            "best_params": best_params,
            "tuning": tuning_summary,
            "walk_forward_model_summary": cv_model_summary.to_dict(orient="records"),
            "oof_predictions": str(
                (reports_dir / "walk_forward_oof_predictions.parquet").resolve()
            ),
            "anchor_population": anchor_dependency,
        }
        _json_dump(reports_dir / "oof_export_report.json", report)
        print("V6 causal OOF export complete; final holdout remained unopened.")
        return report

    print("\n[7/12] Fitting base models and date-balanced calibrating EACH model")
    models = fit_models(train, best_params, processor, cfg)
    y_cal = calibration["wave_entry"].to_numpy(int)
    # Calibration estimates relevance-weighted P(early wave | one stock at one
    # market snapshot). Each date receives equal mass; very late positives keep
    # their label but contribute less according to the documented smooth decay.
    cal_probability_weight = date_balanced_weights(calibration)
    cal_raw = raw_probability_matrix(models, calibration, processor)
    calibrators = fit_individual_calibrators(
        cal_raw, y_cal, cfg.random_seed, cal_probability_weight
    )
    cal_matrix = apply_individual_calibrators(cal_raw, calibrators)

    cal_probs: dict[str, np.ndarray] = {name: cal_matrix[:, pos] for pos, name in enumerate(MODEL_NAMES)}
    cal_thresholds = {
        name: select_threshold(y_cal, cal_probs[name], cal_probability_weight)[0]
        for name in MODEL_NAMES
    }
    cal_metrics_individual = {
        name: classification_metrics(calibration, cal_probs[name], cal_thresholds[name], cfg.top_k_per_day)
        for name in MODEL_NAMES
    }
    cal_base_rate = float(np.average(y_cal, weights=cal_probability_weight))
    cv_summary_by_model = cv_model_summary.set_index("model")
    admission_mask = np.array([
        cal_metrics_individual[name]["roc_auc"] >= cfg.min_model_roc_auc and
        cal_metrics_individual[name]["pr_auc"] >= cal_base_rate * cfg.min_model_pr_lift and
        cal_metrics_individual[name]["lift_at_k"] >= cfg.min_model_top_k_lift and
        bool(cv_summary_by_model.loc[name, "stable_signal"]) and
        float(cv_summary_by_model.loc[name, "pr_lift_mean"]) >= 1.0 and
        float(cv_summary_by_model.loc[name, "lift_at_50_mean"]) >= 1.0
        for name in MODEL_NAMES
    ], dtype=bool)
    active_mask = admission_mask.copy()
    fallback_model: str | None = None
    if not active_mask.any():
        best_pos = int(np.argmax([cal_metrics_individual[name]["pr_auc"] for name in MODEL_NAMES]))
        active_mask[best_pos] = True
        fallback_model = MODEL_NAMES[best_pos]
    admission_rows: list[dict[str, Any]] = []
    for position, name in enumerate(MODEL_NAMES):
        cv_row = cv_summary_by_model.loc[name]
        cal_row = cal_metrics_individual[name]
        admission_rows.append({
            "model": name,
            "calibration_roc_auc": cal_row["roc_auc"],
            "calibration_pr_lift": cal_row["pr_auc"] / max(cal_base_rate, EPS),
            "calibration_lift_at_50": cal_row["lift_at_k"],
            "walk_forward_pr_lift_mean": cv_row["pr_lift_mean"],
            "walk_forward_lift_at_50_mean": cv_row["lift_at_50_mean"],
            "walk_forward_stable_signal": bool(cv_row["stable_signal"]),
            "passed_all_gates": bool(admission_mask[position]),
            "active_for_weight_search": bool(active_mask[position]),
            "fallback_best_model": name == fallback_model,
        })
    model_admission = pd.DataFrame(admission_rows)
    ensemble_weights = learn_ensemble_weights(cal_matrix, calibration, active_mask, cfg)
    if lock_ensemble_weights is not None:
        ensemble_weights = np.asarray(
            [float(lock_ensemble_weights.get(name, 0.0)) for name in MODEL_NAMES],
            dtype=float,
        )
        if np.any(ensemble_weights < 0) or not np.isclose(ensemble_weights.sum(), 1.0):
            raise ValueError("Locked ensemble weights must be non-negative and sum to 1.")
    model_admission["ensemble_weight"] = ensemble_weights
    model_admission.to_csv(reports_dir / "model_ensemble_admission.csv", index=False)
    cal_ensemble_raw = cal_matrix @ ensemble_weights
    ensemble_calibrator = fit_platt_calibrator(
        cal_ensemble_raw, y_cal, cfg.random_seed, cal_probability_weight
    )
    cal_ensemble = apply_platt(ensemble_calibrator, cal_ensemble_raw)
    ensemble_threshold, _ = select_threshold(
        y_cal, cal_ensemble, cal_probability_weight
    )
    cal_probs["ensemble"] = cal_ensemble
    cal_thresholds["ensemble"] = ensemble_threshold
    cal_table = metrics_table(calibration, cal_probs, cal_thresholds, cfg.top_k_per_day)
    cal_table["ranking_k"] = cfg.top_k_per_day
    cal_table.to_csv(reports_dir / "model_metrics_calibration.csv", index=False)
    calibration_reliability_table(calibration, cal_probs).to_csv(
        reports_dir / "probability_reliability_calibration.csv", index=False
    )
    print("\nCalibration model scores:")
    print(cal_table[["model", "pr_auc", "roc_auc", "f1", "precision", "recall", "precision_at_k", "lift_at_k"]].to_string(index=False))
    print("Ensemble weights:", dict(zip(MODEL_NAMES, ensemble_weights.round(4))))

    print("\n[8/12] Locked final holdout: per-model metrics BEFORE trusting ensemble")
    test_raw = raw_probability_matrix(models, test, processor)
    raw_holdout_probability = pd.DataFrame(test_raw, columns=MODEL_NAMES)
    holdout_prediction_export = test[["time", "ticker", "wave_entry"]].reset_index(
        drop=True
    ).copy()
    for model_name in MODEL_NAMES:
        holdout_prediction_export[model_name] = raw_holdout_probability[model_name]
    holdout_prediction_export.to_csv(
        reports_dir / "final_holdout_raw_predictions.csv", index=False
    )
    if set(CANONICAL_MODEL_NAMES).issubset(raw_holdout_probability.columns):
        prediction_correlation, prediction_correlation_summary = (
            prediction_correlation_report(raw_holdout_probability)
        )
        prediction_correlation.to_csv(
            reports_dir / "prediction_correlation_final_holdout.csv",
            index=True,
            index_label="model",
        )
        print_prediction_correlation(
            prediction_correlation,
            str(prediction_correlation_summary["conclusion"]),
        )
    else:
        prediction_correlation_summary = {
            "status": "not_applicable",
            "active_models": list(MODEL_NAMES),
            "reason": "Pearson diversity audit requires XGBoost, LightGBM and CatBoost.",
        }
    test_matrix = apply_individual_calibrators(test_raw, calibrators)
    test_probs: dict[str, np.ndarray] = {name: test_matrix[:, pos] for pos, name in enumerate(MODEL_NAMES)}
    test_probs["ensemble"] = apply_platt(
        ensemble_calibrator,
        test_matrix @ ensemble_weights,
    )
    test_thresholds = dict(cal_thresholds)
    test_table = metrics_table(test, test_probs, test_thresholds, cfg.top_k_per_day)
    test_table["ranking_k"] = cfg.top_k_per_day
    test_table.to_csv(reports_dir / "model_metrics_final_holdout.csv", index=False)
    calibration_reliability_table(test, test_probs).to_csv(
        reports_dir / "probability_reliability_final_holdout.csv", index=False
    )
    print("\nFINAL HOLDOUT model scores:")
    print(test_table[["model", "pr_auc", "roc_auc", "f1", "precision", "recall", "precision_at_k", "lift_at_k", "brier"]].to_string(index=False))

    print("\n[9/12] Backtesting Top 50 realised +50%/+100% outcomes")
    top50_cohorts, top50_backtest_summary = top_k_outcome_backtest(
        test, test_probs["ensemble"], cfg
    )
    top50_cohorts.to_csv(reports_dir / "top50_backtest_cohorts.csv", index=False)
    top50_backtest_summary.to_csv(
        reports_dir / "top50_backtest_by_market_regime.csv", index=False
    )
    holdout_rank_input = test.reset_index(drop=True).copy()
    holdout_rank_input["p_ensemble_pct"] = test_probs["ensemble"] * 100.0
    holdout_rank_input["p_ensemble"] = test_probs["ensemble"]
    holdout_rank_input["model_agreement"] = 1.0 - np.clip(
        test_matrix.std(axis=1) / 0.25, 0, 1
    )
    # Historical market cap is intentionally absent unless a genuine
    # point-in-time series is added later; traded-value percentile is used.
    holdout_rank_detail, holdout_rank_summary = compare_holdout_rankings(
        holdout_rank_input, k=cfg.top_k_per_day, config=PortfolioRankingConfig()
    )
    holdout_rank_detail.to_csv(
        reports_dir / "portfolio_ranking_holdout_before_after.csv", index=False
    )

    print("\n[10/12] Feature importance aligned to the learned ensemble")
    importance = feature_importance_table(models, processor, ensemble_weights)
    importance.to_csv(reports_dir / "feature_importance_aligned.csv", index=False)

    print("\n[11/12] Saving model bundle and evaluation report")
    bundle = {
        "pipeline_version": 6,
        "purpose": "unbounded_early_major_uptrend_probability_ranking",
        "models": models,
        "individual_calibrators": calibrators,
        "ensemble_calibrator": ensemble_calibrator,
        "ensemble_weights": dict(zip(MODEL_NAMES, ensemble_weights)),
        "calibration_method": "date-balanced, lead-time-relevance-weighted Platt scaling per model and ensemble",
        "active_models": dict(zip(MODEL_NAMES, active_mask.tolist())),
        "thresholds": cal_thresholds,
        "feature_experiment": winning_experiment,
        "feature_processor": {
            key: value for key, value in processor.items() if key != "quality_table"
        },
        "best_params": best_params,
        "config": asdict(cfg),
        "split_boundaries": boundaries,
        "data_meta": data_meta,
        "prediction_correlation_final_holdout": prediction_correlation_summary,
    }
    joblib.dump(bundle, models_dir / "evaluation_bundle.joblib", compress=3)

    report: dict[str, Any] = {
        "status": "evaluation_complete",
        "important_note": (
            "No code can guarantee a high out-of-sample score. Probabilities are only meaningful "
            "to the extent that the locked holdout calibration/Brier/PR-AUC remain stable."
        ),
        "config": asdict(cfg),
        "target": data_meta["target_definition"],
        "data": data_meta,
        "split_boundaries": boundaries,
        "walk_forward_folds": [meta for _, _, meta in folds],
        "walk_forward_model_summary": cv_model_summary.to_dict(orient="records"),
        "selected_features": processor["features"],
        "feature_experiment": winning_experiment,
        "feature_group_ablation": ablation.to_dict(orient="records"),
        "tuning": tuning_summary,
        "active_models": dict(zip(MODEL_NAMES, active_mask.tolist())),
        "model_admission": model_admission.to_dict(orient="records"),
        "ensemble_weights": dict(zip(MODEL_NAMES, ensemble_weights)),
        "calibration_method": "date-balanced, lead-time-relevance-weighted Platt scaling per model and ensemble",
        "calibration_metrics": cal_table.to_dict(orient="records"),
        "final_holdout_metrics": test_table.to_dict(orient="records"),
        "prediction_correlation_final_holdout": prediction_correlation_summary,
        "top50_backtest_by_market_regime": top50_backtest_summary.to_dict(orient="records"),
        "portfolio_ranking_holdout_before_after": holdout_rank_summary,
        "limitations": [
            "The label has no fixed horizon; unresolved paths are right-censored and excluded rather than forced negative.",
            "A temporary drawdown does not force a negative label; only a persistent confirmed structural breakdown ends the current setup episode.",
            "Very late positives remain positive but receive a documented smooth relevance discount, so reported probability is relevance-weighted toward detectable precursor states.",
            "Corporate-action policy should preferably be adjusted; large recent jumps are quarantined point-in-time.",
            "Fundamental/news/ownership data are not included in this OHLCV technical model.",
            "Probability calibration must be rechecked after market-regime changes.",
            "Top-50 outcome backtest is a ranking audit, not executable portfolio PnL.",
        ],
    }
    _json_dump(reports_dir / "evaluation_report.json", report)

    print("\n[12/12] Ranking latest market snapshot and exporting TOP 50")
    latest_candidates = panel.loc[panel["eligible"].fillna(False)].copy()
    # Require adequate feature coverage for current ranking too.
    ranking_features = processor["features"]
    latest_candidates = latest_candidates.loc[
        latest_candidates[ranking_features].notna().mean(axis=1) >= cfg.min_row_feature_coverage
    ]
    latest_date = latest_candidates["time"].max()
    latest = latest_candidates.loc[latest_candidates["time"].eq(latest_date)].copy()
    if latest.empty:
        raise RuntimeError("No eligible latest-date candidates survived the quality filters")
    if len(latest) < cfg.min_latest_symbols and not allow_stale_cache:
        raise RuntimeError(
            f"Only {len(latest)} eligible symbols share latest ranking date "
            f"{pd.Timestamp(latest_date).date()}; refresh the complete universe."
        )
    if len(latest) < cfg.latest_top_n:
        warnings.warn(
            f"Only {len(latest)} eligible symbols are available on the latest common scan date; "
            f"the requested Top {cfg.latest_top_n} will be shorter.",
            RuntimeWarning,
        )
    market_cap_map = load_market_cap_map(Path(cfg.market_cap_path))
    latest["market_cap"] = latest["ticker"].map(market_cap_map)
    market_cap_coverage = float(latest["market_cap"].notna().mean())
    latest_raw = raw_probability_matrix(models, latest, processor)
    latest_matrix = apply_individual_calibrators(latest_raw, calibrators)
    latest_ensemble = apply_platt(
        ensemble_calibrator,
        latest_matrix @ ensemble_weights,
    )
    top50 = build_latest_ranking(latest, latest_matrix, latest_ensemble, ensemble_weights, cfg)
    top50.to_csv(reports_dir / "top50_strong_wave_candidates.csv", index=False)
    # Compact human-readable table with an explicit consecutive rank 1..50.
    ranked_summary_columns = [
        "rank", "ticker", "industry", "p_xgb_pct", "p_lgb_pct", "p_cat_pct",
        "p_ensemble_pct", "model_agreement", "active_model_agreement",
        "entry_quality", "setup_status", "actionable_score",
    ]
    top50_ranked_summary = (
        top50.sort_values(["p_ensemble", "model_agreement"], ascending=[False, False])
        .reset_index(drop=True)
        .copy()
    )
    top50_ranked_summary["rank"] = np.arange(1, len(top50_ranked_summary) + 1)
    top50_ranked_summary = top50_ranked_summary[
        [column for column in ranked_summary_columns if column in top50_ranked_summary.columns]
    ]
    top50_ranked_summary.to_csv(
        reports_dir / "top50_ranked_1_to_50.csv", index=False
    )
    # Also save full ranked universe for audit.
    full_ranked = build_latest_ranking(
        latest,
        latest_matrix,
        latest_ensemble,
        ensemble_weights,
        Config(**{**asdict(cfg), "latest_top_n": len(latest)}),
    )
    full_ranked.to_csv(reports_dir / "latest_full_universe_probabilities.csv", index=False)
    actionable_top50 = (
        full_ranked.sort_values(["actionable_score", "p_ensemble"], ascending=[False, False])
        .head(cfg.latest_top_n)
        .copy()
    )
    actionable_top50 = actionable_top50.reset_index(drop=True)
    actionable_top50 = actionable_top50.rename(columns={"rank": "wave_rank"})
    actionable_top50 = actionable_top50.drop(columns=["actionable_rank"], errors="ignore")
    actionable_top50.insert(0, "rank", np.arange(1, len(actionable_top50) + 1))
    actionable_top50.to_csv(reports_dir / "top50_actionable_entries.csv", index=False)

    # Second-stage shortlist.  The calibrated probability is kept intact;
    # accumulation/trend/tradability diagnostics and risk-aware diversification
    # affect ordering only.
    portfolio_top50 = select_diversified_top_k(
        full_ranked, k=cfg.latest_top_n, config=PortfolioRankingConfig()
    )
    portfolio_columns = [
        "portfolio_rank", "ticker", "industry", "p_xgb_pct", "p_lgb_pct",
        "p_cat_pct", "p_ensemble_pct", "wave_probability",
        "accumulation_score", "trend_quality_score", "liquidity_score",
        "base_duration_sessions_estimate", "base_duration_score",
        "volatility_contraction_score", "tight_range_score",
        "volume_accumulation_score", "early_strength_score", "quality_score",
        "size_score", "stability_score", "momentum_quality_score",
        "pump_risk_score", "pump_risk_penalty", "liquidity_penalty",
        "final_score_pre_penalty", "final_score", "portfolio_bucket",
        "market_cap_bucket", "size_basis", "market_cap", "avg_value_traded_20",
        "volatility_60", "entry_quality", "entry_setup_status", "setup_status",
    ]
    portfolio_top50[[c for c in portfolio_columns if c in portfolio_top50]].to_csv(
        reports_dir / "top50_portfolio_ranked.csv", index=False
    )
    before_top50 = full_ranked.sort_values(
        ["p_ensemble", "model_agreement"], ascending=[False, False]
    ).head(cfg.latest_top_n)
    ranking_comparison = {
        "before_wave_probability_only": ranking_profile(before_top50),
        "after_accumulation_risk_and_diversification": ranking_profile(portfolio_top50),
        "market_cap_source": str(Path(cfg.market_cap_path)),
        "market_cap_coverage": market_cap_coverage,
        "important_note": (
            "When market-cap coverage is insufficient, portfolio_bucket uses a "
            "point-in-time traded-value proxy and market_cap_bucket is UNAVAILABLE."
        ),
    }
    _json_dump(reports_dir / "portfolio_ranking_comparison.json", ranking_comparison)

    report["latest_ranking_date"] = str(pd.Timestamp(latest_date).date())
    report["latest_symbols_ranked"] = int(len(latest))
    report["top50_path"] = str(reports_dir / "top50_strong_wave_candidates.csv")
    report["top50_ranked_1_to_50_path"] = str(
        reports_dir / "top50_ranked_1_to_50.csv"
    )
    report["top50_actionable_path"] = str(reports_dir / "top50_actionable_entries.csv")
    report["top50_portfolio_path"] = str(reports_dir / "top50_portfolio_ranked.csv")
    report["portfolio_ranking_comparison"] = ranking_comparison
    report["entry_quality_note"] = (
        "entry_quality is an interpretable 0-100 timing score, not a calibrated probability; "
        "wave probability and entry timing are intentionally reported separately."
    )
    report["second_stage_ranking_note"] = (
        "wave_probability is the calibrated 0-100 model probability. accumulation_score, "
        "trend_quality_score, liquidity_score, and final_score are interpretable ranking "
        "scores, not calibrated probabilities. Label generation, model fitting, features, "
        "and probability calibration are unchanged by this layer."
    )
    _json_dump(reports_dir / "evaluation_report.json", report)

    print("\nTOP 50 strongest-wave probabilities (wave rank 1..50):")
    print(top50[[
        "rank", "ticker", "p_xgb_pct", "p_lgb_pct", "p_cat_pct",
        "p_ensemble_pct", "model_agreement", "entry_quality", "setup_status",
    ]].to_string(index=False))
    print("\nTOP 50 portfolio-ranked candidates (portfolio rank 1..50):")
    print(portfolio_top50[[
        "portfolio_rank", "ticker", "wave_probability", "accumulation_score",
        "trend_quality_score", "liquidity_score", "final_score",
        "portfolio_bucket", "setup_status",
    ]].to_string(index=False))
    print("\nPIPELINE SUMMARY:")
    print(
        f"Symbols: input={data_quality_summary['input_symbols']}, "
        f"loaded={data_quality_summary['loaded_symbols']}; "
        f"samples: eligible={data_quality_summary['eligible_rows']:,}, "
        f"labelled_weekly={len(labelled):,}"
    )
    print(
        f"Features: initial={len(CANDIDATE_FEATURES)}, "
        f"experiment={winning_experiment}, selected={len(processor['features'])}"
    )
    print("Ensemble weights:", dict(zip(MODEL_NAMES, ensemble_weights.round(4))))
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-stale-cache", action="store_true",
        help=(
            "Use existing local CSVs even when snapshot_manifest.json is absent or stale; "
            "this never downloads data."
        ),
    )
    parser.add_argument("--save-feature-store", action="store_true")
    parser.add_argument(
        "--oof-only",
        action="store_true",
        help="Stop after causal walk-forward OOF export; never open final holdout or rank latest rows.",
    )
    parser.add_argument(
        "--rerank-existing", nargs="?",
        const="reports_wave_v6/latest_full_universe_probabilities.csv",
        help=(
            "Only rebuild the accumulation/risk-aware ranking from an existing latest "
            "probability CSV; no model training, calibration, or data download. If no path "
            "is supplied, reports_wave_v6/latest_full_universe_probabilities.csv is used."
        ),
    )
    parser.add_argument("--trials", type=int, default=None)
    parser.add_argument("--compute-device", choices=("cpu", "cuda"), default=None)
    parser.add_argument(
        "--supervised-sample-stride",
        type=int,
        default=None,
        help="Sample every N dates in the selected weekday calendar.",
    )
    parser.add_argument(
        "--supervised-sample-weekday",
        type=int,
        choices=range(5),
        default=None,
        help="Optional ISO weekday selector: Monday=0 through Friday=4.",
    )
    parser.add_argument(
        "--supervised-sample-anchor-date",
        default=None,
        help="Market date that defines phase zero for stride-based sampling.",
    )
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--models-dir", default=None)
    parser.add_argument("--reports-dir", default=None)
    parser.add_argument("--industry-path", default=None)
    parser.add_argument("--market-path", default=None)
    parser.add_argument("--market-cap-path", default=None, help="Optional current symbol/market_cap CSV for latest portfolio ranking.")
    parser.add_argument("--strong-wave-return", type=float, default=None, help="Positive barrier, e.g. 0.50 for +50%%.")
    parser.add_argument(
        "--lead-time-half-life", type=int, default=None,
        help="Smooth relevance half-life for late positives; this is not a label cutoff.",
    )
    parser.add_argument(
        "--price-value-multiplier", type=float, default=None,
        help="Convert quoted close to VND for liquidity; vnstock thousand-VND data uses 1000.",
    )
    parser.add_argument("--top-n", type=int, default=None, help="Latest ranking count; default 50.")
    parser.add_argument("--calibration-sessions", type=int, default=None)
    parser.add_argument("--test-sessions", type=int, default=None)
    parser.add_argument("--evaluation-maturity-sessions", type=int, default=None)
    parser.add_argument(
        "--anchor-dataset-run",
        default=None,
        help="Optional dataset run whose validation population receives fold-local V6 OOF scores.",
    )
    parser.add_argument(
        "--lock-feature-experiment",
        choices=sorted(FEATURE_EXPERIMENTS),
        default=None,
        help="Lock the feature-group candidate set instead of selecting it by ablation.",
    )
    parser.add_argument(
        "--lock-ensemble-weights",
        default=None,
        help="Lock ensemble weights as xgb=0.55,lgb=0,cat=0.45 (must sum to 1).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.rerank_existing is not None:
        defaults = Config()
        rerank_existing_probabilities(
            Path(args.rerank_existing),
            Path(defaults.reports_dir),
            int(args.top_n if args.top_n is not None else defaults.latest_top_n),
        )
        return
    values = asdict(Config())
    for argument, key in (
        (args.trials, "optuna_trials"),
        (args.compute_device, "compute_device"),
        (args.supervised_sample_stride, "supervised_sample_stride"),
        (args.supervised_sample_weekday, "supervised_sample_weekday"),
        (args.supervised_sample_anchor_date, "supervised_sample_anchor_date"),
        (args.data_dir, "data_dir"),
        (args.models_dir, "models_dir"),
        (args.reports_dir, "reports_dir"),
        (args.industry_path, "industry_path"),
        (args.market_path, "market_path"),
        (args.market_cap_path, "market_cap_path"),
        (args.strong_wave_return, "strong_wave_return"),
        (args.lead_time_half_life, "lead_time_half_life_sessions"),
        (args.price_value_multiplier, "price_value_multiplier"),
        (args.top_n, "latest_top_n"),
        (args.calibration_sessions, "calibration_sessions"),
        (args.test_sessions, "test_sessions"),
        (args.evaluation_maturity_sessions, "evaluation_maturity_sessions"),
    ):
        if argument is not None:
            values[key] = argument
    cfg = Config(**values)
    locked_weights = None
    if args.lock_ensemble_weights is not None:
        locked_weights = {}
        for item in args.lock_ensemble_weights.split(","):
            name, separator, value = item.partition("=")
            if not separator or name.strip() not in MODEL_NAMES:
                raise ValueError("--lock-ensemble-weights must use xgb,lgb,cat names")
            locked_weights[name.strip()] = float(value)
    train_pipeline(
        cfg,
        allow_stale_cache=args.allow_stale_cache,
        save_feature_store=args.save_feature_store,
        oof_only=args.oof_only,
        anchor_dataset_run=args.anchor_dataset_run,
        lock_feature_experiment=args.lock_feature_experiment,
        lock_ensemble_weights=locked_weights,
    )


if __name__ == "__main__":
    main()
