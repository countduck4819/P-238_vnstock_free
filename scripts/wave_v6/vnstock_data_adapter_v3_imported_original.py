"""Defensive data adapter for the sponsor-only ``vnstock_data`` package.

The rest of the project should depend on this module instead of importing a
provider class directly.  The adapter prefers the Unified UI introduced by
``vnstock_data`` v3::

    Market().equity("FPT").ohlcv(...)
    Market().index("VNINDEX").ohlcv(...)
    Reference().equity.list()
    Reference().equity.list_by_industry()

``Quote`` is used only as a compatibility fallback for older sponsor package
versions.  ``vnstock_data`` is imported lazily, so cached data and the schema
normalisers remain usable even when the sponsor package is not installed.

Examples
--------
Download and cache one stock::

    python vnstock_data_adapter_v3_imported_original.py stock FPT --start 2015-01-01 --end 2026-08-18

Download VNINDEX and the industry map::

    python vnstock_data_adapter_v3_imported_original.py vnindex --start 2015-01-01 --end 2026-08-18
    python vnstock_data_adapter_v3_imported_original.py industries
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import math
import os
import re
import sys
import warnings
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable, Mapping, Sequence
from uuid import uuid4

import pandas as pd


OHLCV_COLUMNS = ("time", "open", "high", "low", "close", "volume")
EQUITY_COLUMNS = ("symbol", "company_name", "market_cap")
INDUSTRY_COLUMNS = (
    "symbol",
    "industry_code",
    "industry_name",
    "industry_level",
    "company_name",
)

_COLUMN_ALIASES: Mapping[str, Sequence[str]] = {
    "time": (
        "time",
        "date",
        "datetime",
        "timestamp",
        "trading_date",
        "trading_time",
    ),
    "open": ("open", "open_price", "price_open", "openprice", "o"),
    "high": ("high", "high_price", "price_high", "highprice", "h"),
    "low": ("low", "low_price", "price_low", "lowprice", "l"),
    "close": (
        "close",
        "close_price",
        "price_close",
        "closeprice",
        "match_price",
        "c",
    ),
    "volume": (
        "volume",
        "total_volume",
        "match_volume",
        "match_vol",
        "accumulated_volume",
        "vol",
        "v",
    ),
}

_SYMBOL_ALIASES = ("symbol", "ticker", "code", "stock_code", "stock_symbol")
_COMPANY_ALIASES = (
    "company_name",
    "organ_name",
    "org_name",
    "organization_name",
    "name",
)
_MARKET_CAP_ALIASES = (
    "market_cap",
    "marketcap",
    "market_capitalization",
    "capitalization",
    "market_value",
)
_INDUSTRY_CODE_ALIASES = (
    "industry_code",
    "icb_code",
    "icb_code4",
    "icb_code3",
    "icb_code2",
    "icb_code1",
    "icb_code_lv4",
    "icb_code_lv3",
    "icb_code_lv2",
    "sector_code",
)
_INDUSTRY_NAME_ALIASES = (
    "industry_name",
    "icb_name",
    "icb_name4",
    "icb_name3",
    "icb_name2",
    "icb_name1",
    "industry",
    "sector_name",
    "sector",
)
_INDUSTRY_LEVEL_ALIASES = ("industry_level", "icb_level", "level")


def _ohlcv_quality_stats(
    frame: pd.DataFrame,
    price_value_multiplier: float = 1.0,
) -> dict[str, Any]:
    """Snapshot audit only; trainer performs point-in-time eligibility filtering."""
    close = pd.to_numeric(frame["close"], errors="coerce")
    volume = pd.to_numeric(frame["volume"], errors="coerce").fillna(0.0)
    ret = close.pct_change(fill_method=None)
    traded_value = close * volume * price_value_multiplier
    nonzero = volume[volume > 0]
    median_volume = float(nonzero.median()) if not nonzero.empty else 0.0
    median_value = float(traded_value[traded_value > 0].median()) if (traded_value > 0).any() else 0.0
    return {
        "rows": int(len(frame)),
        "zero_volume_ratio": float(volume.eq(0).mean()),
        "median_volume_nonzero": median_volume,
        "median_traded_value": median_value,
        "price_value_multiplier": price_value_multiplier,
        "max_abs_daily_return": float(ret.abs().max()) if ret.notna().any() else None,
        "daily_return_gt_30pct_count": int(ret.abs().gt(0.30).sum()),
        "daily_return_gt_20pct_count": int(ret.abs().gt(0.20).sum()),
    }


def _calendar_alignment_stats(
    frame: pd.DataFrame,
    market_calendar: pd.Series,
) -> dict[str, Any]:
    """Audit stock coverage against VNINDEX sessions without filtering history."""
    stock_dates = pd.DatetimeIndex(pd.to_datetime(frame["time"], errors="coerce").dropna().unique())
    market_dates = pd.DatetimeIndex(
        pd.to_datetime(market_calendar, errors="coerce").dropna().unique()
    ).sort_values()
    if stock_dates.empty or market_dates.empty:
        return {
            "expected_market_sessions_since_listing": 0,
            "observed_market_sessions": 0,
            "missing_market_sessions": 0,
            "market_session_coverage": None,
            "last_market_date_lag_sessions": None,
        }
    first_stock_date = stock_dates.min()
    expected = market_dates[market_dates >= first_stock_date]
    observed = stock_dates.intersection(expected)
    lag = int((market_dates > stock_dates.max()).sum())
    return {
        "expected_market_sessions_since_listing": int(len(expected)),
        "observed_market_sessions": int(len(observed)),
        "missing_market_sessions": int(max(len(expected) - len(observed), 0)),
        "market_session_coverage": float(len(observed) / max(len(expected), 1)),
        "last_market_date_lag_sessions": lag,
    }


class VnstockDataAdapterError(RuntimeError):
    """Base exception raised by this adapter."""


class VnstockDataDependencyError(VnstockDataAdapterError):
    """The sponsor package is missing, incomplete, or incompatible."""


class VnstockDataContractError(VnstockDataAdapterError):
    """A provider response does not satisfy the expected data contract."""


class VnstockDataRequestError(VnstockDataAdapterError):
    """All compatible provider calls failed."""


def _normalise_column_name(value: Any) -> str:
    """Convert a provider column label to a comparable snake-case string."""

    if isinstance(value, tuple):
        value = "_".join(str(part) for part in value if str(part).strip())
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", str(value).strip()).lower()
    text = re.sub(r"[^0-9a-zA-Z]+", "_", text)
    return text.strip("_")


def _column_lookup(frame: pd.DataFrame) -> dict[str, Any]:
    """Map normalised names to original labels, keeping the first match."""

    lookup: dict[str, Any] = {}
    for column in frame.columns:
        lookup.setdefault(_normalise_column_name(column), column)
    return lookup


def _first_column(lookup: Mapping[str, Any], aliases: Iterable[str]) -> Any | None:
    for alias in aliases:
        column = lookup.get(alias)
        if column is not None:
            return column
    return None


def _as_dataframe(value: Any, endpoint: str) -> pd.DataFrame:
    if not isinstance(value, pd.DataFrame):
        raise VnstockDataContractError(
            f"{endpoint} returned {type(value).__name__}, expected pandas.DataFrame."
        )
    if value.empty:
        raise VnstockDataContractError(f"{endpoint} returned an empty DataFrame.")
    return value.copy()


def _parse_time(values: pd.Series) -> pd.Series:
    """Parse common provider timestamps without silently treating epochs as ns."""

    non_null = values.dropna()
    if not non_null.empty and pd.api.types.is_numeric_dtype(non_null):
        numeric = pd.to_numeric(non_null, errors="coerce")
        median = numeric.abs().median()
        as_text = numeric.astype("Int64").astype(str)
        if as_text.str.fullmatch(r"\d{8}").all():
            parsed = pd.to_datetime(values.astype("Int64").astype(str), format="%Y%m%d", errors="coerce")
        elif median >= 1e17:
            parsed = pd.to_datetime(values, unit="ns", errors="coerce", utc=True)
        elif median >= 1e14:
            parsed = pd.to_datetime(values, unit="us", errors="coerce", utc=True)
        elif median >= 1e11:
            parsed = pd.to_datetime(values, unit="ms", errors="coerce", utc=True)
        elif median >= 1e9:
            parsed = pd.to_datetime(values, unit="s", errors="coerce", utc=True)
        else:
            parsed = pd.to_datetime(values, errors="coerce")
    else:
        parsed = pd.to_datetime(values, errors="coerce")

    # Provider data are already expressed in Vietnam/system time.  Remove only
    # timezone metadata; do not shift the wall-clock value and trading date.
    if getattr(parsed.dtype, "tz", None) is not None:
        parsed = parsed.dt.tz_localize(None)
    return parsed


def _to_numeric(values: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(values):
        return pd.to_numeric(values, errors="coerce")
    cleaned = values.astype("string").str.replace(",", "", regex=False).str.strip()
    return pd.to_numeric(cleaned, errors="coerce")


def normalise_ohlcv(frame: pd.DataFrame, *, endpoint: str = "OHLCV") -> pd.DataFrame:
    """Return strictly ordered ``time/open/high/low/close/volume`` data.

    Rows with an invalid timestamp or an incomplete candle are rejected.  The
    function sorts chronologically and keeps the last record for duplicate
    timestamps.  It intentionally does not adjust prices or fill missing bars;
    those decisions belong in the pipeline's data-quality layer.
    """

    data = _as_dataframe(frame, endpoint)
    lookup = _column_lookup(data)

    if _first_column(lookup, _COLUMN_ALIASES["time"]) is None:
        if isinstance(data.index, pd.DatetimeIndex):
            index_name = data.index.name or "time"
            data = data.reset_index().rename(columns={index_name: "time"})
            lookup = _column_lookup(data)
        elif data.index.name and _normalise_column_name(data.index.name) in _COLUMN_ALIASES["time"]:
            data = data.reset_index()
            lookup = _column_lookup(data)

    selected: dict[str, pd.Series] = {}
    missing: list[str] = []
    for canonical in OHLCV_COLUMNS:
        source = _first_column(lookup, _COLUMN_ALIASES[canonical])
        if source is None:
            missing.append(canonical)
        else:
            selected[canonical] = data[source]

    if missing:
        available = ", ".join(map(str, data.columns))
        raise VnstockDataContractError(
            f"{endpoint} is missing required column(s): {', '.join(missing)}. "
            f"Available columns: {available}"
        )

    result = pd.DataFrame(selected)
    result["time"] = _parse_time(result["time"])
    for column in OHLCV_COLUMNS[1:]:
        result[column] = _to_numeric(result[column])

    result = result.replace([float("inf"), float("-inf")], pd.NA)
    before = len(result)
    result = result.dropna(subset=list(OHLCV_COLUMNS))
    if result.empty:
        raise VnstockDataContractError(
            f"{endpoint} has no complete OHLCV rows after schema conversion "
            f"({before} input row(s))."
        )

    # Reject impossible candles instead of letting them silently poison rolling
    # indicators.  Economic filters (liquidity, suspensions, etc.) are NOT done
    # here because filtering a whole ticker with future information would leak.
    valid = (
        result["open"].gt(0) & result["high"].gt(0) & result["low"].gt(0) &
        result["close"].gt(0) & result["volume"].ge(0) &
        result["high"].ge(result[["open", "close", "low"]].max(axis=1)) &
        result["low"].le(result[["open", "close", "high"]].min(axis=1))
    )
    invalid_count = int((~valid).sum())
    result = result.loc[valid].copy()
    if result.empty:
        raise VnstockDataContractError(f"{endpoint} has no valid candles after OHLC sanity checks.")
    if invalid_count:
        warnings.warn(
            f"{endpoint}: dropped {invalid_count}/{before} impossible OHLCV rows.",
            RuntimeWarning,
            stacklevel=2,
        )

    result = (
        result.sort_values("time", kind="stable")
        .drop_duplicates(subset="time", keep="last")
        .reset_index(drop=True)
    )
    return result.loc[:, list(OHLCV_COLUMNS)]


def _clip_ohlcv(frame: pd.DataFrame, start: str, end: str, endpoint: str) -> pd.DataFrame:
    start_time, end_time = pd.Timestamp(start), pd.Timestamp(end)
    clipped = frame.loc[frame["time"].between(start_time, end_time)].reset_index(drop=True)
    if clipped.empty:
        raise VnstockDataContractError(
            f"{endpoint} has no rows inside the requested interval {start}..{end}."
        )
    return clipped


def normalise_equity_list(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalise the minimum useful fields returned by ``equity.list()``."""

    data = _as_dataframe(frame, "Reference().equity.list()")
    lookup = _column_lookup(data)
    symbol_column = _first_column(lookup, _SYMBOL_ALIASES)
    if symbol_column is None:
        raise VnstockDataContractError(
            "Reference().equity.list() has no symbol/ticker column. "
            f"Available columns: {', '.join(map(str, data.columns))}"
        )

    company_column = _first_column(lookup, _COMPANY_ALIASES)
    market_cap_column = _first_column(lookup, _MARKET_CAP_ALIASES)
    result = pd.DataFrame({"symbol": data[symbol_column].astype("string").str.strip().str.upper()})
    result["company_name"] = (
        data[company_column].astype("string").str.strip()
        if company_column is not None
        else pd.Series(pd.NA, index=data.index, dtype="string")
    )
    result["market_cap"] = (
        pd.to_numeric(data[market_cap_column], errors="coerce")
        if market_cap_column is not None
        else pd.Series(float("nan"), index=data.index, dtype=float)
    )
    result = result[result["symbol"].notna() & result["symbol"].ne("")]
    result = result.drop_duplicates("symbol", keep="last").sort_values("symbol").reset_index(drop=True)
    return result.loc[:, list(EQUITY_COLUMNS)]


def normalise_industry_map(
    frame: pd.DataFrame,
    *,
    equities: pd.DataFrame | None = None,
    icb_level: int | None = None,
) -> pd.DataFrame:
    """Create a stable symbol-to-ICB mapping.

    If the provider returns several ICB hierarchy levels per symbol and no
    ``icb_level`` is requested, the most specific (largest) available level is
    retained.  Pass an explicit level when the feature pipeline needs a broad,
    reproducible sector definition.
    """

    data = _as_dataframe(frame, "Reference().equity.list_by_industry()")
    lookup = _column_lookup(data)
    symbol_column = _first_column(lookup, _SYMBOL_ALIASES)
    code_column = _first_column(lookup, _INDUSTRY_CODE_ALIASES)
    name_column = _first_column(lookup, _INDUSTRY_NAME_ALIASES)
    level_column = _first_column(lookup, _INDUSTRY_LEVEL_ALIASES)
    company_column = _first_column(lookup, _COMPANY_ALIASES)

    # VCI commonly returns one row per symbol with a wide ICB hierarchy such
    # as icb_name2/icb_name3/icb_name4 (and matching code columns), rather than
    # one row per hierarchy level.  Resolve that schema explicitly.
    wide_names = {
        level: lookup.get(f"icb_name{level}") or lookup.get(f"icb_name_lv{level}")
        for level in range(1, 5)
    }
    wide_codes = {
        level: lookup.get(f"icb_code{level}") or lookup.get(f"icb_code_lv{level}")
        for level in range(1, 5)
    }
    available_wide_levels = sorted(
        level for level in range(1, 5)
        if wide_names[level] is not None or wide_codes[level] is not None
    )
    selected_wide_level: int | None = None
    if available_wide_levels:
        selected_wide_level = icb_level if icb_level is not None else max(available_wide_levels)
        if selected_wide_level not in available_wide_levels:
            raise VnstockDataContractError(
                f"Industry data contain no wide ICB columns for level {selected_wide_level}; "
                f"available levels are {available_wide_levels}."
            )
        code_column = wide_codes[selected_wide_level]
        name_column = wide_names[selected_wide_level]
        level_column = None

    if symbol_column is None or (code_column is None and name_column is None):
        raise VnstockDataContractError(
            "Reference().equity.list_by_industry() must contain a symbol and "
            "an ICB code or industry name. Available columns: "
            + ", ".join(map(str, data.columns))
        )

    result = pd.DataFrame(index=data.index)
    result["symbol"] = data[symbol_column].astype("string").str.strip().str.upper()
    result["industry_code"] = (
        data[code_column].astype("string").str.strip()
        if code_column is not None
        else pd.Series(pd.NA, index=data.index, dtype="string")
    )
    result["industry_name"] = (
        data[name_column].astype("string").str.strip()
        if name_column is not None
        else pd.Series(pd.NA, index=data.index, dtype="string")
    )
    if selected_wide_level is not None:
        result["industry_level"] = pd.Series(
            selected_wide_level, index=data.index, dtype="Int64"
        )
    else:
        result["industry_level"] = (
            pd.to_numeric(data[level_column], errors="coerce").astype("Int64")
            if level_column is not None
            else pd.Series(pd.NA, index=data.index, dtype="Int64")
        )
    result["company_name"] = (
        data[company_column].astype("string").str.strip()
        if company_column is not None
        else pd.Series(pd.NA, index=data.index, dtype="string")
    )

    result = result[result["symbol"].notna() & result["symbol"].ne("")]
    if icb_level is not None and selected_wide_level is None:
        result = result[result["industry_level"].eq(icb_level)]
        if result.empty:
            raise VnstockDataContractError(
                f"Industry data contain no rows for ICB level {icb_level}."
            )
    elif result["symbol"].duplicated(keep=False).any() and result["industry_level"].notna().any():
        deepest = result.groupby("symbol")["industry_level"].transform("max")
        result = result[result["industry_level"].eq(deepest)]

    if equities is not None:
        equity_names = normalise_equity_list(equities).set_index("symbol")["company_name"]
        result["company_name"] = result["company_name"].fillna(result["symbol"].map(equity_names))

    result = (
        result.drop_duplicates("symbol", keep="last")
        .sort_values("symbol")
        .reset_index(drop=True)
    )
    return result.loc[:, list(INDUSTRY_COLUMNS)]


def _load_vnstock_data() -> ModuleType:
    """Import the sponsor package only when a remote call is required."""

    try:
        return importlib.import_module("vnstock_data")
    except ModuleNotFoundError as exc:
        if exc.name == "vnstock_data":
            raise VnstockDataDependencyError(
                "Không tìm thấy gói sponsor 'vnstock_data' trong Python đang chạy. "
                "Gói này không cài bằng 'pip install vnstock_data'. Hãy cài/kích hoạt "
                "gói Sponsor bằng Vnstock Installer trong đúng môi trường ảo của dự án, "
                "sau đó kiểm tra bằng: python -c \"import vnstock_data\". "
                "Hướng dẫn chính thức: https://vnstocks.com/onboard-member/cai-dat-go-loi"
            ) from exc
        raise VnstockDataDependencyError(
            "Đã tìm thấy 'vnstock_data' nhưng thiếu dependency "
            f"'{exc.name}'. Hãy chạy lại Vnstock Installer trong đúng môi trường ảo."
        ) from exc
    except Exception as exc:
        raise VnstockDataDependencyError(
            "Không thể import 'vnstock_data'. Hãy kiểm tra kích hoạt Sponsor/API key, "
            f"phiên bản Python và môi trường ảo. Chi tiết: {type(exc).__name__}: {exc}"
        ) from exc


def _require_api(module: ModuleType, name: str) -> Any:
    value = getattr(module, name, None)
    if value is None:
        raise VnstockDataDependencyError(
            f"Bản 'vnstock_data' hiện tại không cung cấp {name}. "
            "Hãy cập nhật gói Sponsor bằng Vnstock Installer."
        )
    return value


def _date_string(value: str, label: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must use YYYY-MM-DD format, got {value!r}.") from exc


def _normalise_request(
    symbol: str,
    start: str,
    end: str,
    interval: str,
) -> tuple[str, str, str, str]:
    clean_symbol = symbol.strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9._-]{0,31}", clean_symbol):
        raise ValueError(f"Invalid market symbol: {symbol!r}.")
    clean_start = _date_string(start, "start")
    clean_end = _date_string(end, "end")
    if clean_start > clean_end:
        raise ValueError(f"start ({clean_start}) must not be after end ({clean_end}).")
    clean_interval = interval.strip()
    if not clean_interval or len(clean_interval) > 16 or not re.fullmatch(r"[0-9A-Za-z]+", clean_interval):
        raise ValueError(f"Invalid interval: {interval!r}.")
    return clean_symbol, clean_start, clean_end, clean_interval


def _error_summary(attempts: Sequence[tuple[str, BaseException]]) -> str:
    return "; ".join(
        f"{label}: {type(error).__name__}: {error}" for label, error in attempts
    )


class VnstockDataAdapter:
    """Download, normalise, and cache data used by the modelling pipeline."""

    def __init__(
        self,
        cache_dir: str | Path = "data_vnstock/cache",
        *,
        reference_ttl: timedelta | None = timedelta(days=7),
        legacy_quote_source: str = "VCI",
        allow_legacy_fallback: bool = False,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.reference_ttl = reference_ttl
        self.legacy_quote_source = legacy_quote_source
        self.allow_legacy_fallback = allow_legacy_fallback
        self.last_route = "not_called"

    def _ohlcv_cache_path(
        self,
        asset_type: str,
        symbol: str,
        start: str,
        end: str,
        interval: str,
    ) -> Path:
        safe_interval = re.sub(r"[^0-9A-Za-z]+", "-", interval)
        return self.cache_dir / "ohlcv" / asset_type / f"{symbol}_{start}_{end}_{safe_interval}.csv"

    @staticmethod
    def _cache_is_fresh(path: Path, max_age: timedelta | None) -> bool:
        if not path.is_file():
            return False
        if max_age is None:
            return True
        modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        return datetime.now(timezone.utc) - modified <= max_age

    @staticmethod
    def _write_csv_atomic(frame: pd.DataFrame, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
        try:
            frame.to_csv(temporary, index=False, encoding="utf-8")
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()

    @staticmethod
    def _read_ohlcv_cache(path: Path) -> pd.DataFrame:
        return normalise_ohlcv(pd.read_csv(path), endpoint=f"cache {path}")

    def _call_unified_ohlcv(
        self,
        module: ModuleType,
        *,
        asset_type: str,
        symbol: str,
        start: str,
        end: str,
        interval: str,
    ) -> pd.DataFrame:
        Market = _require_api(module, "Market")
        market = Market()
        branch_factory = getattr(market, asset_type, None)
        if not callable(branch_factory):
            raise VnstockDataDependencyError(
                f"Market() has no callable '{asset_type}' Unified UI branch."
            )
        branch = branch_factory(symbol)
        ohlcv = getattr(branch, "ohlcv", None)
        if not callable(ohlcv):
            raise VnstockDataDependencyError(
                f"Market().{asset_type}({symbol!r}) has no callable ohlcv()."
            )
        raw = ohlcv(start=start, end=end, interval=interval)
        return normalise_ohlcv(
            raw,
            endpoint=f"Market().{asset_type}({symbol!r}).ohlcv()",
        )

    def _call_legacy_quote(
        self,
        module: ModuleType,
        *,
        symbol: str,
        start: str,
        end: str,
        interval: str,
    ) -> pd.DataFrame:
        Quote = _require_api(module, "Quote")
        constructors = (
            lambda: Quote(symbol=symbol, source=self.legacy_quote_source),
            lambda: Quote(source=self.legacy_quote_source, symbol=symbol),
            lambda: Quote(symbol=symbol),
        )
        constructor_errors: list[BaseException] = []
        quote: Any | None = None
        for constructor in constructors:
            try:
                quote = constructor()
                break
            except TypeError as exc:
                constructor_errors.append(exc)
        if quote is None:
            raise VnstockDataDependencyError(
                "Could not construct legacy vnstock_data.Quote: "
                + " | ".join(str(error) for error in constructor_errors)
            )

        history = getattr(quote, "history", None)
        if not callable(history):
            history = getattr(quote, "ohlcv", None)
        if not callable(history):
            raise VnstockDataDependencyError(
                "Legacy vnstock_data.Quote has neither history() nor ohlcv()."
            )
        raw = history(start=start, end=end, interval=interval)
        return normalise_ohlcv(raw, endpoint=f"Quote({symbol!r}).history()")

    def fetch_ohlcv(
        self,
        symbol: str,
        start: str,
        end: str,
        *,
        interval: str = "1D",
        asset_type: str = "equity",
    ) -> pd.DataFrame:
        """Fetch OHLCV without consulting or changing the cache."""

        if asset_type not in {"equity", "index"}:
            raise ValueError("asset_type must be 'equity' or 'index'.")
        symbol, start, end, interval = _normalise_request(symbol, start, end, interval)
        module = _load_vnstock_data()
        attempts: list[tuple[str, BaseException]] = []

        try:
            frame = self._call_unified_ohlcv(
                module,
                asset_type=asset_type,
                symbol=symbol,
                start=start,
                end=end,
                interval=interval,
            )
            self.last_route = f"unified_market_{asset_type}_default"
            return _clip_ohlcv(frame, start, end, self.last_route)
        except Exception as exc:
            attempts.append((f"Unified Market.{asset_type}.ohlcv", exc))

        if self.allow_legacy_fallback and getattr(module, "Quote", None) is not None:
            try:
                frame = self._call_legacy_quote(
                    module,
                    symbol=symbol,
                    start=start,
                    end=end,
                    interval=interval,
                )
                self.last_route = f"legacy_quote_{self.legacy_quote_source}"
                return _clip_ohlcv(frame, start, end, self.last_route)
            except Exception as exc:
                attempts.append(("legacy Quote.history", exc))
        elif self.allow_legacy_fallback:
            attempts.append(
                (
                    "legacy Quote.history",
                    VnstockDataDependencyError("Quote is not exposed by this package version"),
                )
            )
        else:
            attempts.append(
                (
                    "legacy Quote.history",
                    VnstockDataDependencyError(
                        "Legacy fallback is disabled to keep one provider route per snapshot"
                    ),
                )
            )

        raise VnstockDataRequestError(
            f"Không thể tải OHLCV cho {symbol}; cache không bị thay đổi. "
            f"Các lần thử: {_error_summary(attempts)}"
        ) from attempts[-1][1]

    def get_stock_ohlcv(
        self,
        symbol: str,
        start: str,
        end: str,
        *,
        interval: str = "1D",
        refresh: bool = False,
        max_cache_age: timedelta | None = None,
    ) -> pd.DataFrame:
        """Load one equity from cache, or download and cache it atomically."""

        symbol, start, end, interval = _normalise_request(symbol, start, end, interval)
        path = self._ohlcv_cache_path("equity", symbol, start, end, interval)
        if not refresh and self._cache_is_fresh(path, max_cache_age):
            try:
                frame = self._read_ohlcv_cache(path)
                self.last_route = "exact_range_cache"
                return _clip_ohlcv(frame, start, end, self.last_route)
            except Exception as exc:
                warnings.warn(
                    f"Ignoring invalid OHLCV cache {path}: {exc}",
                    RuntimeWarning,
                    stacklevel=2,
                )
        frame = self.fetch_ohlcv(
            symbol,
            start,
            end,
            interval=interval,
            asset_type="equity",
        )
        self._write_csv_atomic(frame, path)
        return frame

    def get_vnindex_ohlcv(
        self,
        start: str,
        end: str,
        *,
        interval: str = "1D",
        refresh: bool = False,
        max_cache_age: timedelta | None = None,
    ) -> pd.DataFrame:
        """Load VNINDEX from cache, or use ``Market().index().ohlcv()``."""

        symbol, start, end, interval = _normalise_request("VNINDEX", start, end, interval)
        path = self._ohlcv_cache_path("index", symbol, start, end, interval)
        if not refresh and self._cache_is_fresh(path, max_cache_age):
            try:
                frame = self._read_ohlcv_cache(path)
                self.last_route = "exact_range_cache"
                return _clip_ohlcv(frame, start, end, self.last_route)
            except Exception as exc:
                warnings.warn(
                    f"Ignoring invalid VNINDEX cache {path}: {exc}",
                    RuntimeWarning,
                    stacklevel=2,
                )
        frame = self.fetch_ohlcv(
            symbol,
            start,
            end,
            interval=interval,
            asset_type="index",
        )
        self._write_csv_atomic(frame, path)
        return frame

    def fetch_equity_list(self) -> pd.DataFrame:
        """Fetch and normalise ``Reference().equity.list()``."""

        module = _load_vnstock_data()
        Reference = _require_api(module, "Reference")
        reference = Reference()
        equity = getattr(reference, "equity", None)
        list_method = getattr(equity, "list", None)
        if not callable(list_method):
            raise VnstockDataDependencyError(
                "Reference().equity.list() is unavailable; update vnstock_data."
            )
        return normalise_equity_list(list_method())

    def get_equity_list(self, *, refresh: bool = False) -> pd.DataFrame:
        path = self.cache_dir / "reference" / "equity_list.csv"
        if not refresh and self._cache_is_fresh(path, self.reference_ttl):
            try:
                return normalise_equity_list(pd.read_csv(path))
            except Exception as exc:
                warnings.warn(
                    f"Ignoring invalid equity-list cache {path}: {exc}",
                    RuntimeWarning,
                    stacklevel=2,
                )
        frame = self.fetch_equity_list()
        self._write_csv_atomic(frame, path)
        return frame

    def fetch_industry_map(
        self,
        *,
        lang: str = "vi",
        icb_level: int | None = None,
    ) -> pd.DataFrame:
        """Fetch the industry map through the sponsor Reference Unified UI."""

        if lang not in {"vi", "en"}:
            raise ValueError("lang must be 'vi' or 'en'.")
        module = _load_vnstock_data()
        Reference = _require_api(module, "Reference")
        reference = Reference()
        equity = getattr(reference, "equity", None)
        industry_method = getattr(equity, "list_by_industry", None)
        list_method = getattr(equity, "list", None)
        if not callable(industry_method):
            raise VnstockDataDependencyError(
                "Reference().equity.list_by_industry() is unavailable; "
                "update vnstock_data."
            )

        try:
            raw_industries = industry_method(lang=lang)
        except TypeError:
            # Compatibility with releases where lang was not exposed.
            raw_industries = industry_method()

        raw_equities: pd.DataFrame | None = None
        if callable(list_method):
            try:
                raw_equities = list_method()
            except Exception as exc:
                warnings.warn(
                    "Industry data were downloaded, but equity.list() could not "
                    f"be used to enrich company names: {exc}",
                    RuntimeWarning,
                    stacklevel=2,
                )
        return normalise_industry_map(
            raw_industries,
            equities=raw_equities,
            icb_level=icb_level,
        )

    def get_industry_map(
        self,
        *,
        lang: str = "vi",
        icb_level: int | None = None,
        refresh: bool = False,
    ) -> pd.DataFrame:
        level_key = "deepest" if icb_level is None else f"level-{icb_level}"
        path = self.cache_dir / "reference" / f"industry_map_{lang}_{level_key}.csv"
        if not refresh and self._cache_is_fresh(path, self.reference_ttl):
            try:
                return normalise_industry_map(pd.read_csv(path), icb_level=icb_level)
            except Exception as exc:
                warnings.warn(
                    f"Ignoring invalid industry-map cache {path}: {exc}",
                    RuntimeWarning,
                    stacklevel=2,
                )
        frame = self.fetch_industry_map(lang=lang, icb_level=icb_level)
        self._write_csv_atomic(frame, path)
        return frame

    @staticmethod
    def _write_json_atomic(payload: Mapping[str, Any], path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
        try:
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def sync_training_snapshot(
        self,
        *,
        start: str,
        end: str,
        stock_dir: str | Path = "data_vnstock",
        market_output: str | Path = "market/VNINDEX.csv",
        industry_output: str | Path = "data_vnstock/industry_map.csv",
        symbols_output: str | Path = "data_vnstock/symbols.csv",
        manifest_output: str | Path = "data_vnstock/snapshot_manifest.json",
        symbols: Sequence[str] | None = None,
        interval: str = "1D",
        force: bool = False,
        icb_level: int | None = None,
        price_policy: str = "provider_default_unverified",
        price_value_multiplier: float = 1_000.0,
    ) -> dict[str, Any]:
        """Synchronise all model inputs to one requested as-of cutoff.

        Remote calls and model training remain separate.  Every successfully
        normalised result is exported atomically to the flat layout consumed by
        ``train_model_6_imported_original.py``.  Failures are recorded rather than hidden.
        """

        start = _date_string(start, "start")
        end = _date_string(end, "end")
        if start > end:
            raise ValueError(f"start ({start}) must not be after end ({end}).")
        if not math.isfinite(price_value_multiplier) or price_value_multiplier <= 0:
            raise ValueError("price_value_multiplier must be a positive finite number.")
        stock_dir = Path(stock_dir)
        market_output = Path(market_output)
        industry_output = Path(industry_output)
        symbols_output = Path(symbols_output)
        manifest_output = Path(manifest_output)

        equity_list = self.get_equity_list(refresh=True)
        if symbols:
            requested = {str(value).strip().upper() for value in symbols if str(value).strip()}
            equity_list = equity_list[equity_list["symbol"].isin(requested)].copy()
            missing = sorted(requested - set(equity_list["symbol"]))
            if missing:
                warnings.warn(f"Symbols absent from Reference.equity.list(): {missing}")
        if equity_list.empty:
            raise VnstockDataContractError("The selected equity universe is empty.")

        industries = self.get_industry_map(icb_level=icb_level, refresh=True)
        refresh_ohlcv = force or price_policy != "provider_default_unverified"
        vnindex = self.get_vnindex_ohlcv(
            start, end, interval=interval, refresh=refresh_ohlcv, max_cache_age=None
        )
        vnindex_route = self.last_route
        self._write_csv_atomic(equity_list, symbols_output)
        self._write_csv_atomic(industries, industry_output)
        self._write_csv_atomic(vnindex, market_output)

        results: dict[str, Any] = {}
        stock_dir.mkdir(parents=True, exist_ok=True)
        universe = equity_list["symbol"].astype(str).str.upper().sort_values().tolist()
        for position, symbol in enumerate(universe, 1):
            output = stock_dir / f"{symbol}.csv"
            try:
                frame = self.get_stock_ohlcv(
                    symbol,
                    start,
                    end,
                    interval=interval,
                    refresh=refresh_ohlcv,
                    max_cache_age=None,
                )
                self._write_csv_atomic(frame, output)
                results[symbol] = {
                    "status": "ok",
                    "rows": int(len(frame)),
                    "min_time": frame["time"].min().isoformat(),
                    "max_time": frame["time"].max().isoformat(),
                    "path": str(output),
                    "sha256": self._sha256(output),
                    "route": self.last_route,
                    "quality": _ohlcv_quality_stats(frame, price_value_multiplier),
                    "calendar_alignment": _calendar_alignment_stats(frame, vnindex["time"]),
                }
            except Exception as exc:
                results[symbol] = {
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                    "path": str(output),
                }
            if position % 25 == 0 or position == len(universe):
                ok = sum(item["status"] == "ok" for item in results.values())
                print(f"Synced {position}/{len(universe)} symbols; ok={ok}; errors={position-ok}")

        try:
            package_version = importlib.metadata.version("vnstock_data")
        except importlib.metadata.PackageNotFoundError:
            package_version = "unknown"
        ok_count = sum(item["status"] == "ok" for item in results.values())
        alignment_records = [
            item["calendar_alignment"] for item in results.values()
            if item.get("status") == "ok" and isinstance(item.get("calendar_alignment"), dict)
        ]
        current_to_vnindex = sum(
            record.get("last_market_date_lag_sessions") == 0 for record in alignment_records
        )
        manifest: dict[str, Any] = {
            "schema_version": 4,
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "requested_start": start,
            "requested_as_of_end": end,
            "interval": interval,
            "provider_package": "vnstock_data",
            "provider_package_version": package_version,
            "provider_route": (
                "Unified Market UI default routing; "
                + (
                    f"legacy Quote fallback explicitly allowed via {self.legacy_quote_source}"
                    if self.allow_legacy_fallback
                    else "legacy Quote fallback disabled"
                )
            ),
            "legacy_quote_source": self.legacy_quote_source,
            "legacy_fallback_allowed": self.allow_legacy_fallback,
            "price_adjustment_policy": price_policy,
            "price_value_multiplier": price_value_multiplier,
            "price_value_note": (
                "Multiplier converts the provider's quoted equity close into VND "
                "for close*volume liquidity calculations; it does not alter OHLC files."
            ),
            "ohlcv_schema": list(OHLCV_COLUMNS),
            "universe_symbols": len(universe),
            "successful_symbols": ok_count,
            "failed_symbols": len(universe) - ok_count,
            "coverage_ratio": ok_count / max(len(universe), 1),
            "calendar_alignment_summary": {
                "symbols_audited": len(alignment_records),
                "symbols_current_to_vnindex": current_to_vnindex,
                "current_to_vnindex_ratio": current_to_vnindex / max(len(alignment_records), 1),
            },
            "vnindex": {
                "rows": int(len(vnindex)),
                "min_time": vnindex["time"].min().isoformat(),
                "max_time": vnindex["time"].max().isoformat(),
                "path": str(market_output),
                "sha256": self._sha256(market_output),
                "route": vnindex_route,
                "quality": _ohlcv_quality_stats(vnindex),
            },
            "industry_map": {
                "rows": int(len(industries)),
                "path": str(industry_output),
                "sha256": self._sha256(industry_output),
            },
            "equity_list": {
                "rows": int(len(equity_list)),
                "path": str(symbols_output),
                "sha256": self._sha256(symbols_output),
            },
            "symbols": results,
        }
        self._write_json_atomic(manifest, manifest_output)
        return manifest


def _add_history_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD).")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD).")
    parser.add_argument("--interval", default="1D", help="Candle interval (default: 1D).")
    parser.add_argument("--refresh", action="store_true", help="Ignore an existing cache file.")
    parser.add_argument(
        "--allow-legacy-fallback",
        action="store_true",
        help="Allow Quote/VCI fallback after Unified UI failure (off by default).",
    )
    parser.add_argument("--output", type=Path, help="Also export the normalised result to this CSV.")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download and cache vnstock_data Sponsor inputs for the stock pipeline."
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("data_vnstock/cache"),
        help="Cache root (default: data_vnstock/cache).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    stock = subparsers.add_parser("stock", help="Fetch one stock's OHLCV data.")
    stock.add_argument("symbol", help="Vietnam equity symbol, for example FPT.")
    _add_history_arguments(stock)

    vnindex = subparsers.add_parser("vnindex", help="Fetch VNINDEX OHLCV data.")
    _add_history_arguments(vnindex)

    industries = subparsers.add_parser("industries", help="Fetch the symbol/industry map.")
    industries.add_argument("--lang", choices=("vi", "en"), default="vi")
    industries.add_argument("--icb-level", type=int)
    industries.add_argument("--refresh", action="store_true")
    industries.add_argument("--output", type=Path)

    equities = subparsers.add_parser("equities", help="Fetch the listed-equity universe.")
    equities.add_argument("--refresh", action="store_true")
    equities.add_argument("--output", type=Path)

    sync = subparsers.add_parser(
        "sync",
        help=(
            "Download/synchronise the complete snapshot and write a manifest. "
            "Do not use this command for already-downloaded CSVs; run train_model_6_imported_original.py "
            "with --allow-stale-cache instead."
        ),
    )
    sync.add_argument("--start", required=True, help="Start date (YYYY-MM-DD).")
    sync.add_argument("--end", required=True, help="Shared as-of cutoff (YYYY-MM-DD).")
    sync.add_argument("--interval", default="1D")
    sync.add_argument("--stock-dir", type=Path, default=Path("data_vnstock"))
    sync.add_argument("--market-output", type=Path, default=Path("market/VNINDEX.csv"))
    sync.add_argument(
        "--industry-output", type=Path, default=Path("data_vnstock/industry_map.csv")
    )
    sync.add_argument("--symbols-output", type=Path, default=Path("data_vnstock/symbols.csv"))
    sync.add_argument(
        "--manifest-output", type=Path,
        default=Path("data_vnstock/snapshot_manifest.json"),
    )
    sync.add_argument(
        "--symbols",
        help="Optional comma-separated subset for debugging; default is all listed equities.",
    )
    sync.add_argument("--icb-level", type=int)
    sync.add_argument("--force", action="store_true", help="Ignore exact-range adapter caches.")
    sync.add_argument(
        "--allow-legacy-fallback",
        action="store_true",
        help="Allow Quote/VCI fallback; strict Unified-only sync is the default.",
    )
    sync.add_argument(
        "--price-policy", default="provider_default_unverified",
        choices=("provider_default_unverified", "raw", "adjusted"),
        help="Record the corporate-action price convention confirmed for this snapshot.",
    )
    sync.add_argument(
        "--price-value-multiplier", type=float, default=1_000.0,
        help="Convert quoted equity price to VND for liquidity metadata (default: 1000).",
    )
    return parser


def _print_summary(frame: pd.DataFrame, label: str) -> None:
    if "time" in frame.columns:
        start = frame["time"].min()
        end = frame["time"].max()
        print(f"{label}: {len(frame):,} rows, {start} -> {end}")
    else:
        print(f"{label}: {len(frame):,} rows")
    print(frame.tail(min(5, len(frame))).to_string(index=False))


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    adapter = VnstockDataAdapter(
        cache_dir=args.cache_dir,
        allow_legacy_fallback=getattr(args, "allow_legacy_fallback", False),
    )

    try:
        if args.command == "stock":
            frame = adapter.get_stock_ohlcv(
                args.symbol,
                args.start,
                args.end,
                interval=args.interval,
                refresh=args.refresh,
            )
            label = args.symbol.strip().upper()
        elif args.command == "vnindex":
            frame = adapter.get_vnindex_ohlcv(
                args.start,
                args.end,
                interval=args.interval,
                refresh=args.refresh,
            )
            label = "VNINDEX"
        elif args.command == "industries":
            frame = adapter.get_industry_map(
                lang=args.lang,
                icb_level=args.icb_level,
                refresh=args.refresh,
            )
            label = "Industry map"
        elif args.command == "equities":
            frame = adapter.get_equity_list(refresh=args.refresh)
            label = "Equity list"

        else:
            manifest = adapter.sync_training_snapshot(
                start=args.start,
                end=args.end,
                stock_dir=args.stock_dir,
                market_output=args.market_output,
                industry_output=args.industry_output,
                symbols_output=args.symbols_output,
                manifest_output=args.manifest_output,
                symbols=args.symbols.split(",") if args.symbols else None,
                interval=args.interval,
                force=args.force,
                icb_level=args.icb_level,
                price_policy=args.price_policy,
                price_value_multiplier=args.price_value_multiplier,
            )
            print(
                "Snapshot complete: "
                f"{manifest['successful_symbols']}/{manifest['universe_symbols']} symbols; "
                f"coverage={manifest['coverage_ratio']:.1%}; "
                f"manifest={args.manifest_output.resolve()}"
            )
            return 0

        if args.output:
            adapter._write_csv_atomic(frame, args.output)
            print(f"Exported: {args.output.resolve()}")
        _print_summary(frame, label)
        return 0
    except (VnstockDataAdapterError, ValueError, OSError, pd.errors.ParserError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
