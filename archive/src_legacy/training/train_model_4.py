"""Leakage-aware wave-entry training pipeline for Vietnamese equities.

This module is intentionally separate from ``train_model_3.py``.  The old file
is kept as a reproducible baseline; this version fixes its evaluation leakage
and implements the core of the proposed Wave Ignition architecture.

Decision convention
-------------------
Features are observed after the close of date ``t``.  The earliest assumed
entry is the next session's open.  Labels only use prices after that entry.
Every split is made by trading date across the whole stock panel, and a sample
is admitted to a training fold only when ``label_end_time < validation_start``.

Data convention
---------------
``vnstock_data_adapter.py`` is responsible for downloading and snapshotting
VNSTOCK_DATA.  This trainer reads those cached snapshots, so experiments remain
repeatable and do not silently change while a model is being trained.
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
from catboost import CatBoostClassifier, CatBoostRegressor
from lightgbm import LGBMClassifier, LGBMRegressor
from scipy.optimize import minimize
from scipy.stats import spearmanr
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    log_loss,
    matthews_corrcoef,
    mean_absolute_error,
    precision_score,
    recall_score,
    roc_auc_score,
)
from xgboost import XGBClassifier, XGBRegressor

EPS = 1e-8


@dataclass(frozen=True)
class Config:
    data_dir: str = "data_vnstock"
    market_path: str = "market/VNINDEX.csv"
    industry_path: str = "data_vnstock/industry_map.csv"
    models_dir: str = "models_wave_v4"
    reports_dir: str = "reports_wave_v4"

    # Wave definition.  All are configurable and must be frozen before test.
    horizon_sessions: int = 150
    target_peak_return: float = 0.45
    min_terminal_return: float = 0.225
    min_future_r2: float = 0.35
    min_future_consistency: float = 0.55
    max_future_drawdown: float = -0.20
    round_trip_cost: float = 0.005

    # Point-in-time eligibility (never filter a whole ticker using its future).
    min_history_sessions: int = 260
    min_avg_volume_30: float = 200_000
    max_zero_volume_ratio_30: float = 0.20

    # Date-level train/calibration/test protocol.
    calibration_sessions: int = 252
    test_sessions: int = 252
    cv_splits: int = 3
    min_cv_train_sessions: int = 504
    min_cv_validation_sessions: int = 63
    optuna_trials: int = 20

    # Cache integrity.  The trainer refuses a severely partial refresh.
    freshness_days: int = 10
    min_fresh_symbols: int = 100
    min_model_symbols: int = 100
    min_snapshot_coverage: float = 0.90
    min_industry_coverage: float = 0.90

    top_k_per_day: int = 10
    random_seed: int = 42


STOCK_FEATURES = [
    "ret_5", "ret_20", "ret_60", "ret_120",
    "price_to_ma20", "price_to_ma50", "price_to_ma200",
    "ma20_to_ma50", "ma50_to_ma200", "ema20_gap", "ema50_gap",
    "slope_20", "slope_60", "trend_r2_20", "trend_r2_60",
    "volatility_20", "volatility_60", "downside_vol_60", "max_dd_60",
    "volume_ratio_20", "volume_trend_20", "log_value_traded_20",
    "breakout_55", "base_contraction", "rsi_14", "macd_norm",
    "macd_signal_norm", "bb_width", "bb_position",
]

MARKET_FEATURES = [
    "market_ret_20", "market_ret_60", "market_price_to_ma200",
    "market_volatility_20", "market_max_dd_60", "market_breadth_ma50",
    "market_breadth_positive_20",
]

SECTOR_FEATURES = [
    "sector_ret_20", "sector_ret_60", "sector_volatility_20",
    "sector_breadth_ma50", "sector_rs_60", "sector_rank_60",
]

LEADER_FEATURES = [
    "stock_rs_market_20", "stock_rs_market_60", "rs_rank_sector_60",
    "volume_rank_sector", "leader_score",
]

FEATURES = STOCK_FEATURES + MARKET_FEATURES + SECTOR_FEATURES + LEADER_FEATURES


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = (
        out.columns.astype(str)
        .str.replace(r"[^\x00-\x7F]+", "", regex=True)
        .str.strip()
        .str.lower()
    )
    aliases = {
        "date": "time", "datetime": "time", "symbol": "ticker",
        "code": "ticker", "industry_name": "industry", "icb_name": "industry",
        "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume",
    }
    return out.rename(columns={k: v for k, v in aliases.items() if k in out.columns})


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
        (df["open"] > 0) & (df["high"] > 0) & (df["low"] > 0) &
        (df["close"] > 0) & (df["high"] >= df[["open", "close", "low"]].max(axis=1)) &
        (df["low"] <= df[["open", "close", "high"]].min(axis=1))
    )
    df.loc[~valid_price, ["open", "high", "low", "close"]] = np.nan
    df.loc[df["volume"] < 0, "volume"] = np.nan
    return df


def align_stock_to_market_calendar(
    stock: pd.DataFrame, market_calendar: pd.Series
) -> pd.DataFrame:
    """Align bars to VNINDEX sessions without inventing executable candles.

    Missing/suspended sessions receive zero volume and a last-known mark close
    solely for trailing valuation/path calculations.  Open/high/low remain
    missing, ``observed`` is false, and such a row can never be an entry signal.
    """
    if stock.empty:
        return stock
    calendar = pd.DatetimeIndex(pd.to_datetime(market_calendar).dropna().unique()).sort_values()
    calendar = calendar[(calendar >= stock["time"].min()) & (calendar <= stock["time"].max())]
    aligned = stock.set_index("time").reindex(calendar)
    aligned.index.name = "time"
    aligned["observed"] = aligned[["open", "high", "low", "close"]].notna().all(axis=1)
    aligned.loc[~aligned["observed"], "volume"] = 0.0
    aligned["volume"] = aligned["volume"].fillna(0.0)
    aligned["close"] = aligned["close"].ffill()
    return aligned.reset_index()


def _rolling_slope_pct(values: np.ndarray) -> float:
    if np.isnan(values).any() or values[-1] <= 0:
        return np.nan
    x = np.arange(values.size, dtype=float)
    slope = np.polyfit(x, values, 1)[0]
    return float(slope / values[-1])


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


def _rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / window, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / window, adjust=False).mean()
    rs = gain / (loss + EPS)
    return 100 - 100 / (1 + rs)


def add_stock_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create strictly backward-looking, mostly scale-free stock features."""
    out = df.copy()
    close, volume = out["close"], out["volume"].fillna(0)
    ret_1 = close.pct_change(fill_method=None)
    out["ret_1"] = ret_1
    for window in (5, 20, 60, 120):
        out[f"ret_{window}"] = close.pct_change(window, fill_method=None)

    ma20, ma50, ma200 = (close.rolling(w).mean() for w in (20, 50, 200))
    ema20, ema50 = close.ewm(span=20, adjust=False).mean(), close.ewm(span=50, adjust=False).mean()
    out["price_to_ma20"] = close / ma20 - 1
    out["price_to_ma50"] = close / ma50 - 1
    out["price_to_ma200"] = close / ma200 - 1
    out["ma20_to_ma50"] = ma20 / ma50 - 1
    out["ma50_to_ma200"] = ma50 / ma200 - 1
    out["ema20_gap"] = close / ema20 - 1
    out["ema50_gap"] = close / ema50 - 1
    out["above_ma50"] = (close > ma50).where(ma50.notna()).astype(float)

    out["slope_20"] = close.rolling(20).apply(_rolling_slope_pct, raw=True)
    out["slope_60"] = close.rolling(60).apply(_rolling_slope_pct, raw=True)
    out["trend_r2_20"] = close.rolling(20).apply(_rolling_r2, raw=True)
    out["trend_r2_60"] = close.rolling(60).apply(_rolling_r2, raw=True)
    out["volatility_20"] = ret_1.rolling(20).std()
    out["volatility_60"] = ret_1.rolling(60).std()
    out["downside_vol_60"] = ret_1.where(ret_1 < 0, 0).rolling(60).std()
    out["max_dd_60"] = close.rolling(60).apply(_rolling_max_drawdown, raw=True)

    vol20 = volume.rolling(20).mean()
    value20 = (close * volume).rolling(20).mean()
    out["volume_ratio_20"] = volume / (vol20 + 1)
    out["volume_trend_20"] = vol20 / vol20.shift(20) - 1
    out["log_value_traded_20"] = np.log1p(value20.clip(lower=0))
    out["avg_volume_30"] = volume.rolling(30).mean()
    out["zero_volume_ratio_30"] = volume.eq(0).rolling(30).mean()
    out["history_sessions"] = np.arange(1, len(out) + 1)

    # Compare today's close with the completed 55-session window ending at t-1.
    # Including today's high would make close / high_55 <= 1 and would encode
    # "distance from the current rolling high", not a true prior-high breakout.
    prior_high_55 = out["high"].shift(1).rolling(55, min_periods=55).max()
    out["breakout_55"] = close / prior_high_55 - 1
    out["base_contraction"] = out["volatility_20"] / (out["volatility_60"] + EPS)
    out["rsi_14"] = _rsi(close)

    ema12, ema26 = close.ewm(span=12, adjust=False).mean(), close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(span=9, adjust=False).mean()
    out["macd_norm"] = macd / close
    out["macd_signal_norm"] = macd_signal / close
    std20 = close.rolling(20).std()
    upper, lower = ma20 + 2 * std20, ma20 - 2 * std20
    out["bb_width"] = (upper - lower) / (ma20 + EPS)
    out["bb_position"] = (close - lower) / (upper - lower + EPS)

    out["eligible"] = (
        (out["history_sessions"] >= 260) &
        (out["avg_volume_30"] >= 200_000) &
        (out["zero_volume_ratio_30"] <= 0.20) &
        out[["open", "high", "low", "close"]].notna().all(axis=1)
    )
    return out


def add_wave_targets(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Attach future event targets using a next-session-open entry convention."""
    out = df.copy()
    n, horizon = len(out), cfg.horizon_sessions
    numeric_targets = [
        "future_peak_return", "future_terminal_return", "future_r2",
        "future_consistency", "future_max_drawdown", "wave_strength",
    ]
    for col in numeric_targets:
        out[col] = np.nan
    out["wave_entry"] = pd.array([pd.NA] * n, dtype="Int8")
    out["entry_time"] = out["time"].shift(-1)
    out["label_end_time"] = out["time"].shift(-horizon)
    if n <= horizon:
        return out

    close = out["close"].to_numpy(float)
    next_open = out["open"].shift(-1).to_numpy(float)
    # Row i receives closes i+1 ... i+horizon (inclusive).
    windows = np.lib.stride_tricks.sliding_window_view(close[1:], horizon)
    m = windows.shape[0]
    entry = next_open[:m]
    valid = np.isfinite(windows).all(axis=1) & np.isfinite(entry) & (entry > 0)

    peak_ret = np.full(m, np.nan)
    terminal_ret = np.full(m, np.nan)
    consistency = np.full(m, np.nan)
    future_dd = np.full(m, np.nan)
    future_r2 = np.full(m, np.nan)
    if valid.any():
        w = windows[valid]
        e = entry[valid, None]
        net_paths = w / e - 1.0 - cfg.round_trip_cost
        peak_ret[valid] = np.max(net_paths, axis=1)
        terminal_ret[valid] = net_paths[:, -1]
        consistency[valid] = np.mean(net_paths > 0, axis=1)
        # Include the executable entry price so an adverse first-session move
        # is part of event drawdown rather than silently ignored.
        path_with_entry = np.concatenate([e, w], axis=1)
        peaks = np.maximum.accumulate(path_with_entry, axis=1)
        future_dd[valid] = np.min(path_with_entry / peaks - 1.0, axis=1)
        x = np.arange(horizon, dtype=float)
        x_centered = x - x.mean()
        y_centered = w - w.mean(axis=1, keepdims=True)
        denom = np.sqrt(np.sum(x_centered ** 2) * np.sum(y_centered ** 2, axis=1))
        corr = np.divide(
            y_centered @ x_centered,
            denom,
            out=np.zeros(w.shape[0], dtype=float),
            where=denom > 0,
        )
        future_r2[valid] = corr ** 2

    entry_label = (
        (peak_ret >= cfg.target_peak_return) &
        (terminal_ret >= cfg.min_terminal_return) &
        (future_r2 >= cfg.min_future_r2) &
        (consistency >= cfg.min_future_consistency) &
        (future_dd >= cfg.max_future_drawdown)
    ).astype(np.int8)
    return_component = np.clip(peak_ret / max(cfg.target_peak_return * 1.5, EPS), 0, 1)
    terminal_component = np.clip(terminal_ret / max(cfg.target_peak_return, EPS), 0, 1)
    drawdown_component = np.clip(1 + future_dd, 0, 1)
    strength = (
        0.35 * return_component + 0.20 * terminal_component +
        0.20 * np.clip(future_r2, 0, 1) +
        0.15 * np.clip(consistency, 0, 1) +
        0.10 * drawdown_component
    )

    idx = out.index[:m]
    out.loc[idx, "future_peak_return"] = peak_ret
    out.loc[idx, "future_terminal_return"] = terminal_ret
    out.loc[idx, "future_r2"] = future_r2
    out.loc[idx, "future_consistency"] = consistency
    out.loc[idx, "future_max_drawdown"] = future_dd
    out.loc[idx, "wave_strength"] = strength
    valid_idx = idx[valid]
    out.loc[valid_idx, "wave_entry"] = entry_label[valid]
    return out


def load_industry_map(path: Path) -> dict[str, str]:
    if not path.exists():
        warnings.warn(
            f"Industry map not found at {path}; sector features will be UNKNOWN. "
            "Run vnstock_data_adapter.py first."
        )
        return {}
    df = _normalise_columns(pd.read_csv(path))
    ticker_col = next((c for c in ("ticker", "symbol") if c in df.columns), None)
    industry_col = next(
        (c for c in ("industry", "industry_name", "icb_name2", "icb_name3", "sector") if c in df.columns),
        None,
    )
    if ticker_col is None or industry_col is None:
        warnings.warn(f"Unrecognised industry schema: {df.columns.tolist()}")
        return {}
    clean = df[[ticker_col, industry_col]].dropna().drop_duplicates(ticker_col, keep="last")
    return dict(zip(clean[ticker_col].astype(str).str.upper(), clean[industry_col].astype(str)))


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


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def add_market_features(index_df: pd.DataFrame) -> pd.DataFrame:
    out = index_df[["time", "close"]].copy().sort_values("time")
    close = out["close"]
    ret1 = close.pct_change(fill_method=None)
    out["market_ret_20"] = close.pct_change(20, fill_method=None)
    out["market_ret_60"] = close.pct_change(60, fill_method=None)
    out["market_price_to_ma200"] = close / close.rolling(200).mean() - 1
    out["market_volatility_20"] = ret1.rolling(20).std()
    out["market_max_dd_60"] = close.rolling(60).apply(_rolling_max_drawdown, raw=True)
    return out.drop(columns="close")


def enrich_cross_sectional_features(panel: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    out = panel.merge(market, on="time", how="left", validate="many_to_one")
    eligible = out.loc[out["eligible"].fillna(False)].copy()
    breadth = eligible.groupby("time", observed=True).agg(
        market_breadth_ma50=("above_ma50", "mean"),
        market_breadth_positive_20=(
            "ret_20", lambda s: float(s.dropna().gt(0).mean()) if s.notna().any() else np.nan
        ),
    ).reset_index()
    out = out.merge(breadth, on="time", how="left", validate="many_to_one")

    sector_daily = eligible.groupby(["industry", "time"], observed=True).agg(
        sector_ret_1=("ret_1", "mean"),
        sector_breadth_ma50=("above_ma50", "mean"),
    ).reset_index().sort_values(["industry", "time"])
    grouped = sector_daily.groupby("industry", observed=True, group_keys=False)
    sector_daily["sector_ret_20"] = grouped["sector_ret_1"].transform(
        lambda s: (1 + s.fillna(0)).rolling(20).apply(np.prod, raw=True) - 1
    )
    sector_daily["sector_ret_60"] = grouped["sector_ret_1"].transform(
        lambda s: (1 + s.fillna(0)).rolling(60).apply(np.prod, raw=True) - 1
    )
    sector_daily["sector_volatility_20"] = grouped["sector_ret_1"].transform(
        lambda s: s.rolling(20).std()
    )
    sector_daily = sector_daily.merge(
        market[["time", "market_ret_60"]], on="time", how="left", validate="many_to_one"
    )
    sector_daily["sector_rs_60"] = (
        sector_daily["sector_ret_60"] - sector_daily["market_ret_60"]
    )
    sector_daily["sector_rank_60"] = sector_daily.groupby("time", observed=True)[
        "sector_rs_60"
    ].rank(pct=True)
    out = out.merge(
        sector_daily.drop(columns=["sector_ret_1", "market_ret_60"]),
        on=["industry", "time"], how="left", validate="many_to_one",
    )
    out["stock_rs_market_20"] = out["ret_20"] - out["market_ret_20"]
    out["stock_rs_market_60"] = out["ret_60"] - out["market_ret_60"]
    out["rs_rank_sector_60"] = out["stock_rs_market_60"].where(out["eligible"]).groupby(
        [out["time"], out["industry"]], observed=True
    ).rank(pct=True)
    out["volume_rank_sector"] = out["volume_ratio_20"].where(out["eligible"]).groupby(
        [out["time"], out["industry"]], observed=True
    ).rank(pct=True)
    out["leader_score"] = (
        0.55 * out["rs_rank_sector_60"] +
        0.25 * out["volume_rank_sector"] +
        0.20 * out["sector_rank_60"]
    )
    return out


def build_panel(cfg: Config, allow_stale_cache: bool = False) -> tuple[pd.DataFrame, dict[str, Any]]:
    data_dir = Path(cfg.data_dir)
    manifest_path = Path(cfg.data_dir) / "snapshot_manifest.json"
    snapshot_manifest: dict[str, Any] | None = None
    if manifest_path.exists():
        try:
            snapshot_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            if not allow_stale_cache:
                raise RuntimeError(f"Invalid snapshot manifest {manifest_path}: {exc}") from exc
    elif not allow_stale_cache:
        raise RuntimeError(
            "Missing data_vnstock/snapshot_manifest.json. Run the vnstock_data adapter "
            "sync command so source, cutoff, schema, and coverage are reproducible."
        )
    if snapshot_manifest is not None:
        coverage = float(snapshot_manifest.get("coverage_ratio", 0.0))
        if coverage < cfg.min_snapshot_coverage and not allow_stale_cache:
            raise RuntimeError(
                f"Snapshot coverage is {coverage:.1%}, below the required "
                f"{cfg.min_snapshot_coverage:.1%}. Re-run the sync and resolve failed symbols."
            )
        price_policy = snapshot_manifest.get("price_adjustment_policy")
        if price_policy not in {"raw", "adjusted"} and not allow_stale_cache:
            raise RuntimeError(
                "Snapshot price-adjustment policy is unverified. Confirm whether the "
                "VNSTOCK_DATA endpoint returns raw or adjusted OHLCV, then rerun sync "
                "with --price-policy raw or --price-policy adjusted."
            )
        try:
            requested_start = pd.Timestamp(snapshot_manifest["requested_start"]).normalize()
            requested_end = pd.Timestamp(snapshot_manifest["requested_as_of_end"]).normalize()
            vnindex_start = pd.Timestamp(snapshot_manifest["vnindex"]["min_time"]).normalize()
            vnindex_end = pd.Timestamp(snapshot_manifest["vnindex"]["max_time"]).normalize()
        except (KeyError, TypeError, ValueError) as exc:
            if not allow_stale_cache:
                raise RuntimeError("Snapshot manifest lacks valid cutoff/VNINDEX dates") from exc
        else:
            if vnindex_end > requested_end and not allow_stale_cache:
                raise RuntimeError(
                    f"VNINDEX contains future rows through {vnindex_end.date()} beyond the "
                    f"requested cutoff {requested_end.date()}."
                )
            if vnindex_start - requested_start > pd.Timedelta(days=45) and not allow_stale_cache:
                raise RuntimeError(
                    f"VNINDEX starts at {vnindex_start.date()}, well after requested start "
                    f"{requested_start.date()}. The historical snapshot appears truncated."
                )
            if requested_end - vnindex_end > pd.Timedelta(days=cfg.freshness_days) and not allow_stale_cache:
                raise RuntimeError(
                    f"VNINDEX stops at {vnindex_end.date()}, too far behind requested cutoff "
                    f"{requested_end.date()}. The provider may have returned a truncated snapshot."
                )
            symbol_records = snapshot_manifest.get("symbols", {})
            successful_records = [
                record for record in symbol_records.values()
                if isinstance(record, dict) and record.get("status") == "ok"
            ]
            legacy_symbols = [
                str(symbol)
                for symbol, record in symbol_records.items()
                if isinstance(record, dict)
                and record.get("status") == "ok"
                and str(record.get("route", "")).startswith("legacy_")
            ]
            vnindex_route = str(snapshot_manifest.get("vnindex", {}).get("route", ""))
            if (legacy_symbols or vnindex_route.startswith("legacy_")) and not allow_stale_cache:
                sample = ", ".join(legacy_symbols[:10]) or "VNINDEX"
                raise RuntimeError(
                    "Snapshot mixes or uses a legacy provider route "
                    f"({sample}). Re-sync in the default strict Unified-only mode so price "
                    "adjustment and units are consistent."
                )
            timely = 0
            future_dated_symbols: list[str] = []
            for symbol, record in symbol_records.items():
                if not isinstance(record, dict) or record.get("status") != "ok":
                    continue
                try:
                    symbol_end = pd.Timestamp(record["max_time"]).normalize()
                    if symbol_end > requested_end:
                        future_dated_symbols.append(str(symbol))
                    timely += int(
                        symbol_end <= requested_end and
                        vnindex_end - symbol_end <= pd.Timedelta(days=cfg.freshness_days)
                    )
                except (KeyError, TypeError, ValueError):
                    continue
            if future_dated_symbols and not allow_stale_cache:
                raise RuntimeError(
                    "Snapshot contains symbols beyond the requested as-of cutoff: "
                    + ", ".join(future_dated_symbols[:10])
                )
            timely_ratio = timely / max(len(successful_records), 1)
            if timely_ratio < cfg.min_snapshot_coverage and not allow_stale_cache:
                raise RuntimeError(
                    f"Only {timely_ratio:.1%} of successful symbols reach the VNINDEX cutoff "
                    f"within {cfg.freshness_days} days. Resolve truncated/stale symbol downloads."
                )

    if snapshot_manifest is not None:
        symbol_records = snapshot_manifest.get("symbols", {})
        successful = {
            str(symbol).upper(): record
            for symbol, record in symbol_records.items()
            if isinstance(record, dict) and record.get("status") == "ok"
        }
        files = [data_dir / f"{symbol}.csv" for symbol in sorted(successful)]
        integrity_errors: list[str] = []
        for path in files:
            record = successful[path.stem.upper()]
            expected_hash = record.get("sha256")
            if not path.is_file():
                integrity_errors.append(f"missing:{path.name}")
            elif not expected_hash:
                integrity_errors.append(f"no_hash:{path.name}")
            elif file_sha256(path) != expected_hash:
                integrity_errors.append(f"hash_mismatch:{path.name}")
        for label, path, record_key in (
            ("vnindex", Path(cfg.market_path), "vnindex"),
            ("industry", Path(cfg.industry_path), "industry_map"),
        ):
            record = snapshot_manifest.get(record_key, {})
            expected_hash = record.get("sha256") if isinstance(record, dict) else None
            if not path.is_file():
                integrity_errors.append(f"missing:{label}:{path}")
            elif not expected_hash:
                integrity_errors.append(f"no_hash:{label}:{path}")
            elif file_sha256(path) != expected_hash:
                integrity_errors.append(f"hash_mismatch:{label}:{path}")
        if integrity_errors and not allow_stale_cache:
            sample = ", ".join(integrity_errors[:10])
            raise RuntimeError(
                "Snapshot integrity check failed; files and manifest are from different "
                f"sync states ({sample}). Re-run vnstock_data_adapter.py sync."
            )
        if integrity_errors and allow_stale_cache:
            warnings.warn(f"Ignoring snapshot integrity errors in debug mode: {integrity_errors[:10]}")
        files = [path for path in files if path.is_file()]
    else:
        files = sorted(
            p for p in data_dir.glob("*.csv")
            if p.name.lower() not in {"industry_map.csv", "symbols.csv"}
        )

    freshness = cache_freshness(files, cfg)
    if freshness["fresh_symbols"] < cfg.min_fresh_symbols and not allow_stale_cache:
        raise RuntimeError(
            "Partial/stale cache detected: only "
            f"{freshness['fresh_symbols']} successful snapshot symbols are within "
            f"{cfg.freshness_days} days of the newest file ({freshness['newest_date']}). "
            "Refresh the complete universe with vnstock_data_adapter.py."
        )

    market_raw = load_ohlcv(Path(cfg.market_path))
    market = add_market_features(market_raw)
    industries = load_industry_map(Path(cfg.industry_path))
    if not industries and not allow_stale_cache:
        raise RuntimeError(
            "Industry map is required for the Wave v4 sector/leader layer. "
            "Run `python vnstock_data_adapter.py industries --output "
            "data_vnstock/industry_map.csv`, or use --allow-stale-cache only for debugging."
        )
    industry_coverage = sum(path.stem.upper() in industries for path in files) / max(len(files), 1)
    if industry_coverage < cfg.min_industry_coverage and not allow_stale_cache:
        raise RuntimeError(
            f"Industry-map coverage is {industry_coverage:.1%}, below the required "
            f"{cfg.min_industry_coverage:.1%}. Sync a fixed ICB level (for example --icb-level 2)."
        )
    rows: list[pd.DataFrame] = []
    failures: dict[str, str] = {}
    for pos, path in enumerate(files, 1):
        ticker = path.stem.upper()
        try:
            stock = load_ohlcv(path)
            stock = align_stock_to_market_calendar(stock, market_raw["time"])
            if len(stock) <= max(cfg.min_history_sessions, cfg.horizon_sessions):
                continue
            stock = add_stock_features(stock)
            # Config owns eligibility thresholds; overwrite defaults from feature helper.
            stock["eligible"] = (
                (stock["history_sessions"] >= cfg.min_history_sessions) &
                (stock["avg_volume_30"] >= cfg.min_avg_volume_30) &
                (stock["zero_volume_ratio_30"] <= cfg.max_zero_volume_ratio_30) &
                stock[["open", "high", "low", "close"]].notna().all(axis=1)
            )
            stock = add_wave_targets(stock, cfg)
            stock["ticker"] = ticker
            stock["industry"] = industries.get(ticker, "UNKNOWN")
            rows.append(stock)
        except Exception as exc:
            failures[ticker] = f"{type(exc).__name__}: {exc}"
        if pos % 100 == 0:
            print(f"Loaded {pos}/{len(files)} files; usable={len(rows)}; failed={len(failures)}")
    if not rows:
        raise RuntimeError("No stock data survived schema and history checks")
    if len(rows) < cfg.min_model_symbols and not allow_stale_cache:
        raise RuntimeError(
            f"Only {len(rows)} symbols survived schema/history checks; at least "
            f"{cfg.min_model_symbols} are required for the main experiment."
        )

    panel = pd.concat(rows, ignore_index=True, sort=False)
    panel = enrich_cross_sectional_features(panel, market)
    panel.replace([np.inf, -np.inf], np.nan, inplace=True)
    meta = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "freshness": freshness,
        "loaded_symbols": int(panel["ticker"].nunique()),
        "unknown_industry_symbols": int(panel.loc[panel["industry"].eq("UNKNOWN"), "ticker"].nunique()),
        "industry_coverage": industry_coverage,
        "failed_symbols": len(failures),
        "failure_sample": dict(list(failures.items())[:25]),
        "date_min": str(panel["time"].min().date()),
        "date_max": str(panel["time"].max().date()),
    }
    if snapshot_manifest is not None:
        meta["snapshot_manifest"] = snapshot_manifest
    else:
        meta["snapshot_manifest_warning"] = (
            "Missing snapshot_manifest.json; source version, as-of cutoff, and "
            "corporate-action price policy are not reproducible."
        )
    return panel.sort_values(["time", "ticker"]).reset_index(drop=True), meta


def prepare_samples(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return labelled modelling samples and latest unlabelled inference rows."""
    feature_ok = panel[FEATURES].notna().all(axis=1)
    common = panel["eligible"].fillna(False) & feature_ok
    labelled = panel.loc[
        common & panel["wave_entry"].notna() & panel["label_end_time"].notna()
    ].copy()
    labelled["wave_entry"] = labelled["wave_entry"].astype(int)

    unlabelled = panel.loc[common & panel["wave_entry"].isna()].copy()
    return (
        labelled.sort_values(["time", "ticker"]).reset_index(drop=True),
        unlabelled.sort_values(["time", "ticker"]).reset_index(drop=True),
    )


def split_train_calibration_test(
    labelled: pd.DataFrame, cfg: Config
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, str]]:
    dates = np.array(sorted(labelled["time"].dropna().unique()))
    # Reserve an embargo of one full label horizon before the final test while
    # still retaining ``calibration_sessions`` effective calibration dates.
    calibration_span = cfg.calibration_sessions + cfg.horizon_sessions
    required = (
        cfg.min_cv_train_sessions + cfg.cv_splits * cfg.min_cv_validation_sessions +
        2 * cfg.horizon_sessions +
        calibration_span + cfg.test_sessions
    )
    if len(dates) < required:
        raise RuntimeError(
            f"Only {len(dates)} labelled trading dates are available; at least {required} "
            "are required for inner walk-forward, calibration, and final test."
        )
    calibration_start = pd.Timestamp(dates[-(calibration_span + cfg.test_sessions)])
    test_start = pd.Timestamp(dates[-cfg.test_sessions])

    # label_end_time is the exact event horizon.  These predicates implement
    # purging without confusing panel rows with trading sessions.
    train = labelled.loc[
        (labelled["time"] < calibration_start) &
        (labelled["label_end_time"] < calibration_start)
    ].copy()
    calibration = labelled.loc[
        (labelled["time"] >= calibration_start) &
        (labelled["time"] < test_start) &
        (labelled["label_end_time"] < test_start)
    ].copy()
    test = labelled.loc[labelled["time"] >= test_start].copy()
    for name, frame in (("train", train), ("calibration", calibration), ("test", test)):
        if frame.empty or frame["wave_entry"].nunique() < 2:
            raise RuntimeError(f"{name} split is empty or contains only one class")
    boundaries = {
        "calibration_start": str(calibration_start.date()),
        "test_start": str(test_start.date()),
        "train_last_label_end": str(train["label_end_time"].max().date()),
        "calibration_last_label_end": str(calibration["label_end_time"].max().date()),
    }
    return train, calibration, test, boundaries


def purged_walk_forward_folds(
    train: pd.DataFrame, cfg: Config
) -> list[tuple[np.ndarray, np.ndarray, dict[str, str]]]:
    dates = np.array(sorted(train["time"].unique()))
    first_validation_pos = cfg.min_cv_train_sessions + cfg.horizon_sessions
    remaining = len(dates) - first_validation_pos
    if remaining < cfg.cv_splits * cfg.min_cv_validation_sessions:
        raise RuntimeError("Not enough training dates for the requested walk-forward folds")
    validation_size = remaining // cfg.cv_splits
    folds: list[tuple[np.ndarray, np.ndarray, dict[str, str]]] = []
    for fold in range(cfg.cv_splits):
        start_pos = first_validation_pos + fold * validation_size
        end_pos = len(dates) if fold == cfg.cv_splits - 1 else start_pos + validation_size
        validation_start = pd.Timestamp(dates[start_pos])
        validation_end_exclusive = (
            pd.Timestamp(dates[end_pos]) if end_pos < len(dates) else pd.Timestamp.max
        )
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
    if "history_sessions" in ordered.columns:
        previous_session = ordered.groupby("ticker", observed=True)["history_sessions"].shift()
        consecutive = ordered["history_sessions"].eq(previous_session + 1)
    else:
        previous_time = ordered.groupby("ticker", observed=True)["time"].shift()
        consecutive = ordered["time"].sub(previous_time).dt.days.le(4)
    new_run = ordered["wave_entry"].ne(previous) | ~consecutive
    run_id = new_run.groupby(ordered["ticker"]).cumsum()
    run_size = ordered.groupby([ordered["ticker"], run_id], observed=True)[
        "wave_entry"
    ].transform("size").to_numpy(float)
    event_weight_ordered = np.where(y_ordered == 1, 1.0 / np.maximum(run_size, 1), 1.0)
    return pd.Series(event_weight_ordered, index=ordered.index).reindex(frame.index).to_numpy(float)


def balanced_event_weights(frame: pd.DataFrame) -> np.ndarray:
    event_weight = event_uniqueness_weights(frame)
    y = frame["wave_entry"].to_numpy(int)
    negatives = max(int((1 - y).sum()), 1)
    positive_event_mass = max(float(event_weight[y == 1].sum()), 1.0)
    class_multiplier = negatives / positive_event_mass
    weights = event_weight * np.where(y == 1, class_multiplier, 1.0)
    return weights / max(weights.mean(), EPS)


def suggest_classifier_params(model_name: str, trial: optuna.Trial) -> dict[str, Any]:
    common = {
        "n_estimators": trial.suggest_int("n_estimators", 150, 450),
        "max_depth": trial.suggest_int("max_depth", 3, 7),
        "learning_rate": trial.suggest_float("learning_rate", 0.015, 0.12, log=True),
    }
    if model_name == "xgb":
        return {
            **common,
            "min_child_weight": trial.suggest_float("min_child_weight", 3, 15),
            "subsample": trial.suggest_float("subsample", 0.65, 0.95),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.65, 0.95),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-4, 2.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 0.1, 5.0, log=True),
        }
    if model_name == "lgb":
        common.pop("max_depth")
        return {
            **common,
            "num_leaves": trial.suggest_int("num_leaves", 15, 63),
            "max_depth": trial.suggest_int("max_depth", 3, 7),
            "min_child_samples": trial.suggest_int("min_child_samples", 30, 150),
            "subsample": trial.suggest_float("subsample", 0.65, 0.95),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.65, 0.95),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-4, 2.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 0.1, 5.0, log=True),
        }
    if model_name == "cat":
        return {
            "iterations": common["n_estimators"],
            "depth": common["max_depth"],
            "learning_rate": common["learning_rate"],
            "l2_leaf_reg": trial.suggest_float("l2_leaf_reg", 1.0, 12.0),
            "random_strength": trial.suggest_float("random_strength", 0.0, 2.0),
        }
    raise KeyError(model_name)


def make_classifier(model_name: str, params: dict[str, Any], seed: int):
    if model_name == "xgb":
        return XGBClassifier(
            **params, objective="binary:logistic", eval_metric="logloss",
            random_state=seed, n_jobs=-1,
        )
    if model_name == "lgb":
        return LGBMClassifier(
            **params, subsample_freq=1, random_state=seed, n_jobs=-1, verbosity=-1
        )
    if model_name == "cat":
        return CatBoostClassifier(
            **params, random_seed=seed, verbose=False, allow_writing_files=False,
        )
    raise KeyError(model_name)


def tune_classifier(
    model_name: str,
    train: pd.DataFrame,
    folds: list[tuple[np.ndarray, np.ndarray, dict[str, str]]],
    cfg: Config,
) -> tuple[dict[str, Any], dict[str, Any]]:
    X = train[FEATURES].to_numpy(np.float32)
    y = train["wave_entry"].to_numpy(int)

    def objective(trial: optuna.Trial) -> float:
        params = suggest_classifier_params(model_name, trial)
        scores: list[float] = []
        for train_idx, val_idx, _ in folds:
            fold_train = train.iloc[train_idx]
            model = make_classifier(model_name, params, cfg.random_seed)
            model.fit(
                X[train_idx], y[train_idx],
                sample_weight=balanced_event_weights(fold_train),
            )
            probability = model.predict_proba(X[val_idx])[:, 1]
            scores.append(average_precision_score(y[val_idx], probability))
        trial.set_user_attr("fold_scores", scores)
        return float(np.mean(scores) - 0.10 * np.std(scores))

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=cfg.random_seed),
        study_name=f"wave_v4_{model_name}",
    )
    study.optimize(objective, n_trials=cfg.optuna_trials, show_progress_bar=True)
    summary = {
        "best_objective": float(study.best_value),
        "best_fold_scores": [float(x) for x in study.best_trial.user_attrs.get("fold_scores", [])],
        "trials": cfg.optuna_trials,
    }
    best_params = suggest_classifier_params(
        model_name, optuna.trial.FixedTrial(study.best_params)
    )
    return best_params, summary


def fit_classifiers(
    frame: pd.DataFrame,
    params: dict[str, dict[str, Any]],
    seed: int,
) -> dict[str, Any]:
    X, y = frame[FEATURES].to_numpy(np.float32), frame["wave_entry"].to_numpy(int)
    weights = balanced_event_weights(frame)
    models: dict[str, Any] = {}
    for name in ("xgb", "lgb", "cat"):
        model = make_classifier(name, params[name], seed)
        model.fit(X, y, sample_weight=weights)
        models[name] = model
    return models


def predict_matrix(models: dict[str, Any], frame: pd.DataFrame) -> np.ndarray:
    X = frame[FEATURES].to_numpy(np.float32)
    return np.column_stack([models[name].predict_proba(X)[:, 1] for name in ("xgb", "lgb", "cat")])


def learn_ensemble_weights(probabilities: np.ndarray, y: np.ndarray) -> np.ndarray:
    def objective(weights: np.ndarray) -> float:
        p = np.clip(probabilities @ weights, 1e-6, 1 - 1e-6)
        return float(log_loss(y, p))

    result = minimize(
        objective,
        x0=np.full(probabilities.shape[1], 1 / probabilities.shape[1]),
        method="SLSQP",
        bounds=[(0.0, 1.0)] * probabilities.shape[1],
        constraints={"type": "eq", "fun": lambda w: float(w.sum() - 1)},
    )
    if not result.success:
        warnings.warn(f"Ensemble optimisation failed ({result.message}); using equal weights")
        return np.full(probabilities.shape[1], 1 / probabilities.shape[1])
    return np.asarray(result.x, dtype=float)


def fit_platt_calibrator(raw_probability: np.ndarray, y: np.ndarray) -> LogisticRegression:
    raw = np.clip(raw_probability, 1e-6, 1 - 1e-6)
    logit = np.log(raw / (1 - raw)).reshape(-1, 1)
    calibrator = LogisticRegression(C=1.0, solver="lbfgs", random_state=42)
    calibrator.fit(logit, y)
    return calibrator


def apply_calibrator(calibrator: LogisticRegression, raw_probability: np.ndarray) -> np.ndarray:
    raw = np.clip(raw_probability, 1e-6, 1 - 1e-6)
    logit = np.log(raw / (1 - raw)).reshape(-1, 1)
    return calibrator.predict_proba(logit)[:, 1]


def select_threshold(y: np.ndarray, probability: np.ndarray) -> tuple[float, float]:
    candidates = np.unique(np.quantile(probability, np.linspace(0.02, 0.98, 97)))
    best_threshold, best_f1 = 0.5, -1.0
    for threshold in candidates:
        score = f1_score(y, probability >= threshold, zero_division=0)
        if score > best_f1:
            best_threshold, best_f1 = float(threshold), float(score)
    return best_threshold, best_f1


def expected_calibration_error(y: np.ndarray, probability: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0, 1, bins + 1)
    total, ece = len(y), 0.0
    for left, right in zip(edges[:-1], edges[1:]):
        mask = (probability >= left) & (probability < right if right < 1 else probability <= right)
        if mask.any():
            ece += mask.mean() * abs(float(y[mask].mean()) - float(probability[mask].mean()))
    return float(ece if total else np.nan)


def precision_at_k_by_date(
    frame: pd.DataFrame, probability: np.ndarray, k: int
) -> dict[str, float]:
    scored = frame[["time", "wave_entry"]].copy()
    scored["probability"] = probability
    top = (
        scored.sort_values(["time", "probability"], ascending=[True, False])
        .groupby("time", observed=True)
        .head(k)
    )
    daily = top.groupby("time", observed=True)["wave_entry"].mean()
    precision = float(top["wave_entry"].mean()) if not top.empty else float("nan")
    base_rate = float(scored["wave_entry"].mean())
    return {
        "precision_at_k": precision,
        "lift_at_k": precision / max(base_rate, EPS),
        "daily_precision_mean": float(daily.mean()),
        "days_evaluated": int(daily.size),
    }


def classification_metrics(
    frame: pd.DataFrame, probability: np.ndarray, threshold: float, top_k: int
) -> dict[str, Any]:
    y = frame["wave_entry"].to_numpy(int)
    prediction = (probability >= threshold).astype(int)
    uniqueness = event_uniqueness_weights(frame)
    positive_events = int(round(float(uniqueness[y == 1].sum())))
    result: dict[str, Any] = {
        "samples": int(len(y)),
        "positive_rate": float(y.mean()),
        "positives": int(y.sum()),
        "pr_auc": float(average_precision_score(y, probability)),
        "event_weighted_pr_auc": float(
            average_precision_score(y, probability, sample_weight=uniqueness)
        ),
        "positive_event_runs": positive_events,
        "roc_auc": float(roc_auc_score(y, probability)),
        "brier": float(brier_score_loss(y, probability)),
        "log_loss": float(log_loss(y, np.clip(probability, 1e-6, 1 - 1e-6))),
        "ece_10_bins": expected_calibration_error(y, probability),
        "threshold": float(threshold),
        "precision": float(precision_score(y, prediction, zero_division=0)),
        "recall": float(recall_score(y, prediction, zero_division=0)),
        "f1": float(f1_score(y, prediction, zero_division=0)),
        "mcc": float(matthews_corrcoef(y, prediction)),
        "confusion_matrix": confusion_matrix(y, prediction).tolist(),
    }
    result.update(precision_at_k_by_date(frame, probability, top_k))
    return result


def block_bootstrap_pr_auc(
    frame: pd.DataFrame,
    probability: np.ndarray,
    seed: int,
    repeats: int = 200,
    block_length: int = 20,
) -> dict[str, float]:
    scored = frame[["time", "wave_entry"]].copy()
    scored["probability"] = probability
    groups = {date: group for date, group in scored.groupby("time", observed=True)}
    dates = np.array(list(groups))
    rng, values = np.random.default_rng(seed), []
    block_length = max(1, min(int(block_length), len(dates)))
    blocks_needed = math.ceil(len(dates) / block_length)
    for _ in range(repeats):
        starts = rng.integers(0, len(dates) - block_length + 1, size=blocks_needed)
        sampled_dates = np.concatenate(
            [dates[start:start + block_length] for start in starts]
        )[:len(dates)]
        sample = pd.concat([groups[date] for date in sampled_dates], ignore_index=True)
        if sample["wave_entry"].nunique() == 2:
            values.append(average_precision_score(sample["wave_entry"], sample["probability"]))
    if not values:
        return {"pr_auc_ci_low": float("nan"), "pr_auc_ci_high": float("nan")}
    return {
        "pr_auc_ci_low": float(np.quantile(values, 0.025)),
        "pr_auc_ci_high": float(np.quantile(values, 0.975)),
    }


def make_strength_regressor(model_name: str, seed: int):
    if model_name == "xgb":
        return XGBRegressor(
            n_estimators=300, max_depth=5, learning_rate=0.04,
            subsample=0.8, colsample_bytree=0.8, reg_lambda=2.0,
            objective="reg:squarederror", random_state=seed, n_jobs=-1,
        )
    if model_name == "lgb":
        return LGBMRegressor(
            n_estimators=300, num_leaves=31, max_depth=6, learning_rate=0.04,
            subsample=0.8, colsample_bytree=0.8, reg_lambda=2.0,
            subsample_freq=1, random_state=seed, n_jobs=-1, verbosity=-1,
        )
    if model_name == "cat":
        return CatBoostRegressor(
            iterations=300, depth=6, learning_rate=0.04, l2_leaf_reg=5.0,
            loss_function="MAE", random_seed=seed, verbose=False,
            allow_writing_files=False,
        )
    raise KeyError(model_name)


def fit_strength_models(frame: pd.DataFrame, seed: int) -> dict[str, Any]:
    positive_mask = frame["wave_entry"].eq(1) & frame["wave_strength"].notna()
    positive = frame.loc[positive_mask].copy()
    if len(positive) < 100:
        raise RuntimeError(f"Only {len(positive)} positive events are available for strength regression")
    X = positive[FEATURES].to_numpy(np.float32)
    y = positive["wave_strength"].to_numpy(float)
    weights = event_uniqueness_weights(frame)[positive_mask.to_numpy()]
    models: dict[str, Any] = {}
    for name in ("xgb", "lgb", "cat"):
        model = make_strength_regressor(name, seed)
        model.fit(X, y, sample_weight=weights)
        models[name] = model
    return models


def predict_strength_matrix(models: dict[str, Any], frame: pd.DataFrame) -> np.ndarray:
    X = frame[FEATURES].to_numpy(np.float32)
    return np.clip(
        np.column_stack([models[name].predict(X) for name in ("xgb", "lgb", "cat")]),
        0,
        1,
    )


def learn_regression_weights(predictions: np.ndarray, target: np.ndarray) -> np.ndarray:
    result = minimize(
        lambda w: float(np.mean(np.abs(target - predictions @ w))),
        x0=np.full(predictions.shape[1], 1 / predictions.shape[1]),
        method="SLSQP",
        bounds=[(0.0, 1.0)] * predictions.shape[1],
        constraints={"type": "eq", "fun": lambda w: float(w.sum() - 1)},
    )
    if not result.success:
        return np.full(predictions.shape[1], 1 / predictions.shape[1])
    return np.asarray(result.x, dtype=float)


def strength_metrics(frame: pd.DataFrame, predicted_strength: np.ndarray) -> dict[str, float]:
    mask = frame["wave_entry"].eq(1).to_numpy() & frame["wave_strength"].notna().to_numpy()
    actual = frame.loc[mask, "wave_strength"].to_numpy(float)
    predicted = predicted_strength[mask]
    correlation = spearmanr(actual, predicted).statistic if len(actual) >= 3 else np.nan
    return {
        "positive_samples": int(mask.sum()),
        "mae": float(mean_absolute_error(actual, predicted)) if len(actual) else float("nan"),
        "spearman_rank_ic": float(correlation) if np.isfinite(correlation) else float("nan"),
    }


def feature_importance_table(models: dict[str, Any], weights: np.ndarray) -> pd.DataFrame:
    table = pd.DataFrame({"feature": FEATURES})
    combined = np.zeros(len(FEATURES), dtype=float)
    for position, name in enumerate(("xgb", "lgb", "cat")):
        importance = np.asarray(models[name].feature_importances_, dtype=float)
        if importance.size != len(FEATURES):
            raise RuntimeError(f"{name} returned {importance.size} importances for {len(FEATURES)} features")
        normalised = importance / max(importance.sum(), EPS)
        table[f"importance_{name}"] = normalised
        combined += weights[position] * normalised
    table["importance_ensemble"] = combined
    return table.sort_values("importance_ensemble", ascending=False).reset_index(drop=True)


def generate_shap_importance(
    models: dict[str, Any],
    weights: np.ndarray,
    frame: pd.DataFrame,
    output_path: Path,
    seed: int,
    max_samples: int = 2_000,
) -> None:
    """Create aligned global SHAP importance without affecting model selection."""
    try:
        import shap  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "SHAP was requested but is not installed. Install a compatible pinned "
            "version, then rerun with --shap."
        ) from exc
    sample = frame.sample(min(max_samples, len(frame)), random_state=seed)
    X = sample[FEATURES]
    report = pd.DataFrame({"feature": FEATURES})
    combined = np.zeros(len(FEATURES), dtype=float)
    for position, name in enumerate(("xgb", "lgb", "cat")):
        explanation = shap.TreeExplainer(models[name])(X)
        values = np.asarray(explanation.values)
        if values.ndim == 3:
            values = values[:, :, -1]
        importance = np.mean(np.abs(values), axis=0)
        importance = importance / max(float(importance.sum()), EPS)
        report[f"mean_abs_shap_{name}"] = importance
        combined += weights[position] * importance
    report["mean_abs_shap_ensemble"] = combined
    report.sort_values("mean_abs_shap_ensemble", ascending=False).to_csv(output_path, index=False)


def add_ranking_columns(
    frame: pd.DataFrame,
    probability: np.ndarray,
    conditional_strength: np.ndarray,
) -> pd.DataFrame:
    ranked = frame[["time", "ticker", "industry", "close", "volume"]].copy()
    for audit_column in ("wave_entry", "wave_strength", "future_peak_return"):
        if audit_column in frame.columns:
            ranked[audit_column] = frame[audit_column]
    ranked["wave_probability"] = probability
    ranked["conditional_wave_strength"] = conditional_strength
    ranked["expected_wave_strength"] = probability * conditional_strength

    # Risk weights are fixed before the holdout.  They are intentionally simple
    # until a cost-aware backtest supplies evidence for a more complex engine.
    volatility_rank = frame.groupby("time", observed=True)["volatility_60"].rank(pct=True)
    drawdown_rank = (-frame["max_dd_60"]).groupby(frame["time"]).rank(pct=True)
    illiquidity_rank = (-frame["log_value_traded_20"]).groupby(frame["time"]).rank(pct=True)
    ranked["risk_score"] = 0.45 * volatility_rank + 0.35 * drawdown_rank + 0.20 * illiquidity_rank
    ranked["ranking_score"] = (
        0.65 * ranked["wave_probability"] +
        0.25 * ranked["expected_wave_strength"] -
        0.10 * ranked["risk_score"]
    )
    ranked["rank"] = ranked.groupby("time", observed=True)["ranking_score"].rank(
        method="first", ascending=False
    ).astype(int)
    return ranked.sort_values(["time", "rank"])


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

    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=convert),
        encoding="utf-8",
    )


def _discarded_refactored_train_pipeline(
    cfg: Config,
    allow_stale_cache: bool = False,
    save_feature_store: bool = False,
    generate_shap: bool = False,
    evaluate_final_test: bool = False,
    run_id: str | None = None,
) -> dict[str, Any]:
    run_id = run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    version_root = Path(cfg.output_root) / cfg.model_version
    runs_root = version_root / "runs"
    final_run_dir = runs_root / run_id
    run_dir = runs_root / f".incomplete-{run_id}"
    if final_run_dir.exists() or run_dir.exists():
        raise FileExistsError(f"Wave v4 run already exists: {run_id}")
    model_dir, reports_dir = run_dir / "model", run_dir / "reports"
    model_dir.mkdir(parents=True, exist_ok=False)
    reports_dir.mkdir(parents=True, exist_ok=False)
    completed = False

    try:
        print("\n[1/8] Building point-in-time feature panel")
        panel, data_meta = build_panel(cfg, allow_stale_cache=allow_stale_cache)
        labelled, unlabelled = prepare_samples(panel)
        model_symbols = int(labelled["ticker"].nunique())
        if model_symbols < cfg.min_model_symbols and not allow_stale_cache:
            raise RuntimeError(
                f"Only {model_symbols} symbols have eligible labelled samples; at least "
                f"{cfg.min_model_symbols} are required to avoid a narrow-universe model."
            )
        data_meta.update({
            "labelled_samples": int(len(labelled)),
            "inference_samples": int(len(unlabelled)),
            "labelled_positive_rate": float(labelled["wave_entry"].mean()),
            "model_symbols": model_symbols,
            "features": FEATURES,
        })
        if save_feature_store:
            feature_store_path = run_dir / "feature_store_wave_v4.joblib"
            joblib.dump(
                panel[[
                    "time", "ticker", "industry", "entry_time", "label_end_time",
                    "eligible", "wave_entry", "wave_strength", *FEATURES,
                ]],
                feature_store_path,
                compress=3,
            )
            data_meta["feature_store_path"] = str(final_run_dir / feature_store_path.name)

        print("\n[2/8] Creating purged date-level splits")
        train, calibration, test, boundaries = split_train_calibration_test(
            labelled, cfg, validate_test_labels=evaluate_final_test
        )
        blend, probability_calibration, meta_boundaries = split_meta_calibration(
            calibration, cfg
        )
        folds = purged_walk_forward_folds(train, cfg)
        fold_meta = [meta for _, _, meta in folds]
        print(
            f"Train={len(train):,}, blend={len(blend):,}, "
            f"probability-calibration={len(probability_calibration):,}; "
            f"sealed test starts {boundaries['test_start']}"
        )

        print("\n[3/8] Tuning classifiers with purged expanding walk-forward")
        best_params: dict[str, dict[str, Any]] = {}
        tuning_summary: dict[str, Any] = {}
        for name in ("xgb", "lgb", "cat"):
            print(f"Tuning {name.upper()}...")
            best_params[name], tuning_summary[name] = tune_classifier(name, train, folds, cfg)

        print("\n[4/8] Fitting classifiers and temporally separated meta layers")
        evaluation_models = fit_classifiers(
            train, best_params, cfg.random_seed, n_jobs=cfg.n_jobs
        )
        blend_matrix = predict_matrix(evaluation_models, blend)
        y_blend = blend["wave_entry"].to_numpy(int)
        base_calibrators = fit_base_calibrators(blend_matrix, y_blend)
        blend_calibrated_matrix = apply_base_calibrators(base_calibrators, blend_matrix)
        classifier_weights = learn_ensemble_weights(
            blend_calibrated_matrix, y_blend, event_uniqueness_weights(blend)
        )
        probability_matrix = predict_matrix(evaluation_models, probability_calibration)
        probability_base_calibrated = apply_base_calibrators(
            base_calibrators, probability_matrix
        )
        y_probability = probability_calibration["wave_entry"].to_numpy(int)
        probability_raw = probability_base_calibrated @ classifier_weights
        calibrator = fit_platt_calibrator(probability_raw, y_probability)
        calibrated_probability = apply_calibrator(calibrator, probability_raw)
        threshold, calibration_f1 = select_threshold(y_probability, calibrated_probability)

        print("\n[5/8] Fitting Wave Strength regressors")
        strength_rounds = select_strength_rounds(train, folds[-1], cfg)
        strength_models = fit_strength_models(
            train,
            cfg.random_seed,
            n_jobs=cfg.n_jobs,
            rounds=strength_rounds,
        )
        positive_blend = blend["wave_entry"].eq(1).to_numpy()
        blend_strength_matrix = predict_strength_matrix(strength_models, blend)
        strength_weights = learn_regression_weights(
            blend_strength_matrix[positive_blend],
            blend.loc[positive_blend, "wave_strength"].to_numpy(float),
        )
        probability_strength = (
            predict_strength_matrix(strength_models, probability_calibration) @ strength_weights
        )
        calibration_metrics = classification_metrics(
            probability_calibration,
            calibrated_probability,
            threshold,
            cfg.top_k_per_day,
        )
        calibration_strength_metrics = strength_metrics(
            probability_calibration, probability_strength
        )

        print("\n[6/8] Respecting the final-holdout access policy")
        test_metrics: dict[str, Any] | None = None
        strength_test_metrics: dict[str, Any] | None = None
        comparisons: dict[str, Any] = {}
        if evaluate_final_test:
            test_matrix = predict_matrix(evaluation_models, test)
            test_base_calibrated = apply_base_calibrators(base_calibrators, test_matrix)
            test_raw = test_base_calibrated @ classifier_weights
            test_probability = apply_calibrator(calibrator, test_raw)
            test_strength = predict_strength_matrix(strength_models, test) @ strength_weights
            test_metrics = classification_metrics(
                test, test_probability, threshold, cfg.top_k_per_day
            )
            test_metrics.update(block_bootstrap_pr_auc(
                test,
                test_probability,
                cfg.random_seed,
                block_length=cfg.horizon_sessions,
            ))
            strength_test_metrics = strength_metrics(test, test_strength)
            for position, name in enumerate(("xgb", "lgb", "cat")):
                single_cal_probability = probability_base_calibrated[:, position]
                single_threshold, _ = select_threshold(y_probability, single_cal_probability)
                single_test_probability = test_base_calibrated[:, position]
                comparisons[f"{name}_calibrated"] = classification_metrics(
                    test, single_test_probability, single_threshold, cfg.top_k_per_day
                )
            equal_calibrator = fit_platt_calibrator(
                probability_matrix.mean(axis=1), y_probability
            )
            equal_cal_probability = apply_calibrator(
                equal_calibrator, probability_matrix.mean(axis=1)
            )
            equal_threshold, _ = select_threshold(y_probability, equal_cal_probability)
            comparisons["equal_weight_calibrated"] = classification_metrics(
                test,
                apply_calibrator(equal_calibrator, test_matrix.mean(axis=1)),
                equal_threshold,
                cfg.top_k_per_day,
            )
            raw_threshold, _ = select_threshold(y_probability, probability_raw)
            comparisons["learned_ensemble_raw"] = classification_metrics(
                test, test_raw, raw_threshold, cfg.top_k_per_day
            )
            comparisons["learned_ensemble_calibrated"] = test_metrics
            add_ranking_columns(test, test_probability, test_strength).to_csv(
                reports_dir / "final_holdout_rankings.csv", index=False
            )

        importance = feature_importance_table(evaluation_models, classifier_weights)
        importance.to_csv(reports_dir / "feature_importance_aligned.csv", index=False)
        if generate_shap:
            shap_frame = test if evaluate_final_test else probability_calibration
            shap_name = (
                "shap_importance_final_holdout.csv"
                if evaluate_final_test
                else "shap_importance_probability_calibration.csv"
            )
            generate_shap_importance(
                evaluation_models,
                classifier_weights,
                shap_frame,
                reports_dir / shap_name,
                cfg.random_seed,
            )

        print("\n[7/8] Saving isolated model and audit artifacts")
        config_payload = asdict(cfg)
        config_sha256 = hashlib.sha256(
            json.dumps(config_payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        evaluation_bundle = {
            "pipeline_version": 4,
            "model_version": cfg.model_version,
            "run_id": run_id,
            "purpose": "sealed_holdout_evaluation_and_candidate_inference",
            "features": FEATURES,
            "classifiers": evaluation_models,
            "base_calibrators": base_calibrators,
            "classifier_weights": dict(zip(("xgb", "lgb", "cat"), classifier_weights)),
            "platt_calibration": {
                "intercept": float(calibrator.intercept_[0]),
                "slope": float(calibrator.coef_[0, 0]),
            },
            "calibrator": calibrator,
            "threshold": threshold,
            "strength_models": strength_models,
            "strength_rounds": strength_rounds,
            "strength_weights": dict(zip(("xgb", "lgb", "cat"), strength_weights)),
            "best_params": best_params,
            "config": config_payload,
            "configuration_sha256": config_sha256,
            "split_boundaries": {**boundaries, **meta_boundaries},
            "base_model_trained_through_feature_date": str(train["time"].max().date()),
            "base_model_trained_through_label_end_date": str(
                train["label_end_time"].max().date()
            ),
            "data_meta": data_meta,
        }
        joblib.dump(evaluation_bundle, model_dir / "evaluation_bundle.joblib", compress=3)

        report: dict[str, Any] = {
            "status": (
                "final_holdout_evaluated_not_investment_validation"
                if evaluate_final_test
                else "pre_final_evaluation_complete_holdout_sealed"
            ),
            "model_version": cfg.model_version,
            "run_id": run_id,
            "run_directory": str(final_run_dir.resolve()),
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "configuration_sha256": config_sha256,
            "config": config_payload,
            "data": data_meta,
            "split_boundaries": {**boundaries, **meta_boundaries},
            "walk_forward_folds": fold_meta,
            "tuning": tuning_summary,
            "strength_rounds": strength_rounds,
            "classifier_weights": dict(zip(("xgb", "lgb", "cat"), classifier_weights)),
            "platt_calibration": evaluation_bundle["platt_calibration"],
            "strength_weights": dict(zip(("xgb", "lgb", "cat"), strength_weights)),
            "calibration_f1_used_for_threshold_selection": calibration_f1,
            "probability_calibration_metrics": calibration_metrics,
            "probability_calibration_strength_metrics": calibration_strength_metrics,
            "final_test_evaluated": evaluate_final_test,
            "final_holdout_metrics": test_metrics,
            "final_holdout_model_comparison": comparisons,
            "final_holdout_strength_metrics": strength_test_metrics,
            "limitations": [
                "No transaction-cost/slippage/capacity backtest has been run.",
                "Industry mapping is current-snapshot unless a point-in-time map is supplied.",
                "Provider corporate-action adjustment policy must be recorded in the ingestion manifest.",
                "Calibration can drift when the market regime changes and must be monitored.",
                "No all-data production refit is emitted without new OOF meta predictions.",
                "OHLCV/market/industry data is not a complete CAN SLIM fundamental model.",
            ],
        }

        print("\n[8/8] Ranking the latest snapshot with the locked calibrated bundle")
        if not unlabelled.empty:
            latest_date = unlabelled["time"].max()
            latest = unlabelled.loc[unlabelled["time"].eq(latest_date)].copy()
            if not latest.empty:
                latest_matrix = predict_matrix(evaluation_models, latest)
                latest_base_calibrated = apply_base_calibrators(
                    base_calibrators, latest_matrix
                )
                latest_probability = apply_calibrator(
                    calibrator, latest_base_calibrated @ classifier_weights
                )
                latest_strength = (
                    predict_strength_matrix(strength_models, latest) @ strength_weights
                )
                latest_ranking = add_ranking_columns(
                    latest, latest_probability, latest_strength
                )
                latest_ranking["selected_at_locked_threshold"] = (
                    latest_ranking["wave_probability"] >= threshold
                )
                latest_ranking.to_csv(reports_dir / "latest_opportunities.csv", index=False)
                report["latest_ranking_date"] = str(pd.Timestamp(latest_date).date())
                report["latest_symbols_ranked"] = int(len(latest_ranking))
        _json_dump(reports_dir / "evaluation_report.json", report)
        _json_dump(
            run_dir / "run_manifest.json",
            {
                "model_version": cfg.model_version,
                "run_id": run_id,
                "generated_at_utc": report["generated_at_utc"],
                "configuration_sha256": config_sha256,
                "final_test_evaluated": evaluate_final_test,
                "test_policy": "Final holdout is scored only with --evaluate-final-test.",
            },
        )
        run_dir.rename(final_run_dir)
        _json_dump(
            version_root / "latest.json",
            {
                "model_version": cfg.model_version,
                "run_id": run_id,
                "run_directory": str(final_run_dir.resolve()),
                "generated_at_utc": report["generated_at_utc"],
                "final_test_evaluated": evaluate_final_test,
            },
        )
        completed = True
        if test_metrics is None:
            print("Final holdout remains sealed; use --evaluate-final-test exactly once when approved.")
        else:
            print(
                "Final holdout: "
                f"PR-AUC={test_metrics['pr_auc']:.4f}, "
                f"P@{cfg.top_k_per_day}={test_metrics['precision_at_k']:.4f}, "
                f"Brier={test_metrics['brier']:.4f}, F1={test_metrics['f1']:.4f}"
            )
        return report
    finally:
        if not completed and run_dir.exists():
            shutil.rmtree(run_dir)


def train_pipeline(
    cfg: Config,
    allow_stale_cache: bool = False,
    save_feature_store: bool = False,
    generate_shap: bool = False,
) -> dict[str, Any]:
    """Run the original v4 training, calibration, and holdout workflow."""
    models_dir = Path(cfg.models_dir)
    reports_dir = Path(cfg.reports_dir)
    models_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    print("\n[1/8] Building point-in-time feature panel")
    panel, data_meta = build_panel(cfg, allow_stale_cache=allow_stale_cache)
    labelled, unlabelled = prepare_samples(panel)
    model_symbols = int(labelled["ticker"].nunique())
    if model_symbols < cfg.min_model_symbols and not allow_stale_cache:
        raise RuntimeError(
            f"Only {model_symbols} symbols have eligible labelled samples; at least "
            f"{cfg.min_model_symbols} are required to avoid a narrow-universe model."
        )
    data_meta.update({
        "labelled_samples": int(len(labelled)),
        "inference_samples": int(len(unlabelled)),
        "labelled_positive_rate": float(labelled["wave_entry"].mean()),
        "model_symbols": model_symbols,
        "features": FEATURES,
    })
    if save_feature_store:
        joblib.dump(
            panel[[
                "time", "ticker", "industry", "entry_time", "label_end_time",
                "eligible", "wave_entry", "wave_strength", *FEATURES,
            ]],
            models_dir / "feature_store_wave_v4.joblib",
            compress=3,
        )

    print("\n[2/8] Creating purged date-level splits")
    train, calibration, test, boundaries = split_train_calibration_test(labelled, cfg)
    folds = purged_walk_forward_folds(train, cfg)

    print("\n[3/8] Tuning classifiers with purged expanding walk-forward")
    best_params: dict[str, dict[str, Any]] = {}
    tuning_summary: dict[str, Any] = {}
    for name in ("xgb", "lgb", "cat"):
        print(f"Tuning {name.upper()}...")
        best_params[name], tuning_summary[name] = tune_classifier(name, train, folds, cfg)

    print("\n[4/8] Fitting classifiers and calibration layer")
    classifiers = fit_classifiers(train, best_params, cfg.random_seed)
    calibration_matrix = predict_matrix(classifiers, calibration)
    calibration_target = calibration["wave_entry"].to_numpy(int)
    classifier_weights = learn_ensemble_weights(calibration_matrix, calibration_target)
    calibration_raw = calibration_matrix @ classifier_weights
    calibrator = fit_platt_calibrator(calibration_raw, calibration_target)
    calibration_probability = apply_calibrator(calibrator, calibration_raw)
    threshold, calibration_f1 = select_threshold(
        calibration_target, calibration_probability
    )

    print("\n[5/8] Fitting Wave Strength regressors")
    strength_models = fit_strength_models(train, cfg.random_seed)
    positive_calibration = calibration["wave_entry"].eq(1).to_numpy()
    calibration_strength_matrix = predict_strength_matrix(strength_models, calibration)
    strength_weights = learn_regression_weights(
        calibration_strength_matrix[positive_calibration],
        calibration.loc[positive_calibration, "wave_strength"].to_numpy(float),
    )

    print("\n[6/8] Evaluating final holdout")
    test_matrix = predict_matrix(classifiers, test)
    test_probability = apply_calibrator(
        calibrator, test_matrix @ classifier_weights
    )
    test_strength = predict_strength_matrix(strength_models, test) @ strength_weights
    test_metrics = classification_metrics(
        test, test_probability, threshold, cfg.top_k_per_day
    )
    test_metrics.update(block_bootstrap_pr_auc(
        test,
        test_probability,
        cfg.random_seed,
        block_length=cfg.horizon_sessions,
    ))
    test_strength_metrics = strength_metrics(test, test_strength)
    add_ranking_columns(test, test_probability, test_strength).to_csv(
        reports_dir / "final_holdout_rankings.csv", index=False
    )

    print("\n[7/8] Saving model and audit artifacts")
    classifier_weights_dict = dict(zip(("xgb", "lgb", "cat"), classifier_weights))
    strength_weights_dict = dict(zip(("xgb", "lgb", "cat"), strength_weights))
    bundle = {
        "pipeline_version": 4,
        "features": FEATURES,
        "classifiers": classifiers,
        "classifier_weights": classifier_weights_dict,
        "calibrator": calibrator,
        "threshold": threshold,
        "strength_models": strength_models,
        "strength_weights": strength_weights_dict,
        "best_params": best_params,
        "config": asdict(cfg),
        "split_boundaries": boundaries,
        "data_meta": data_meta,
    }
    joblib.dump(bundle, models_dir / "wave_ensemble_v4.joblib", compress=3)
    feature_importance_table(classifiers, classifier_weights).to_csv(
        reports_dir / "feature_importance_aligned.csv", index=False
    )
    if generate_shap:
        generate_shap_importance(
            classifiers,
            classifier_weights,
            test,
            reports_dir / "shap_importance_final_holdout.csv",
            cfg.random_seed,
        )

    report: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "config": asdict(cfg),
        "data": data_meta,
        "split_boundaries": boundaries,
        "walk_forward_folds": [metadata for _, _, metadata in folds],
        "tuning": tuning_summary,
        "classifier_weights": classifier_weights_dict,
        "strength_weights": strength_weights_dict,
        "calibration_f1_used_for_threshold_selection": calibration_f1,
        "final_holdout_metrics": test_metrics,
        "final_holdout_strength_metrics": test_strength_metrics,
    }

    print("\n[8/8] Ranking the latest snapshot")
    if not unlabelled.empty:
        latest_date = unlabelled["time"].max()
        latest = unlabelled.loc[unlabelled["time"].eq(latest_date)].copy()
        if not latest.empty:
            latest_probability = apply_calibrator(
                calibrator, predict_matrix(classifiers, latest) @ classifier_weights
            )
            latest_strength = (
                predict_strength_matrix(strength_models, latest) @ strength_weights
            )
            add_ranking_columns(latest, latest_probability, latest_strength).to_csv(
                reports_dir / "latest_opportunities.csv", index=False
            )
    _json_dump(reports_dir / "training_report.json", report)
    print(
        f"Final holdout: PR-AUC={test_metrics['pr_auc']:.4f}, "
        f"P@{cfg.top_k_per_day}={test_metrics['precision_at_k']:.4f}, "
        f"Brier={test_metrics['brier']:.4f}, F1={test_metrics['f1']:.4f}"
    )
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-stale-cache", action="store_true",
        help="Debug only: bypass the cross-symbol freshness gate.",
    )
    parser.add_argument(
        "--save-feature-store", action="store_true",
        help="Persist the full point-in-time panel (can be several hundred MB).",
    )
    parser.add_argument(
        "--shap", action="store_true",
        help="Generate global SHAP importance on the final test.",
    )
    parser.add_argument("--trials", type=int, default=Config.optuna_trials)
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--industry-path", default=None)
    parser.add_argument("--market-path", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    values = asdict(Config())
    for argument, key in (
        (args.trials, "optuna_trials"),
        (args.data_dir, "data_dir"),
        (args.industry_path, "industry_path"),
        (args.market_path, "market_path"),
    ):
        if argument is not None:
            values[key] = argument
    cfg = Config(**values)
    train_pipeline(
        cfg,
        allow_stale_cache=args.allow_stale_cache,
        save_feature_store=args.save_feature_store,
        generate_shap=args.shap,
    )


if __name__ == "__main__":
    main()
