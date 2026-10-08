import json
import math
import os
import re
import tempfile
import threading
import time
import traceback
from datetime import datetime, timedelta

import pandas as pd
try:
    from vnstock_data import Fundamental, Market
except ImportError:
    from vnstock import Fundamental, Market

from core.paths import data_path

CACHE_DIR = data_path("finance")

# Đổi version để cache rỗng/sai schema cũ tự động được fetch lại.
CACHE_VERSION = 3

# Ratio không nên cache 1 năm.
# 12 tiếng sẽ đủ nhẹ API nhưng dữ liệu không bị quá cũ.
CACHE_TTL_HOURS = 12

# Chỉ giữ 8 kỳ gần nhất.
MAX_PERIODS = 8

_last_call = 0
_request_rate_lock = threading.Lock()
_finance_locks = {}
_finance_locks_guard = threading.Lock()
_finance_flights = set()
_finance_flights_guard = threading.Lock()

FINANCE_REQUEST_DELAY_SECONDS = float(
    os.environ.get("FINANCE_REQUEST_DELAY_SECONDS", "0.5")
)

_PERIOD_COLUMN_RE = re.compile(
    r"^(\d{4}(?:-Q[1-4])?)(?:_\d+)?$",
    re.IGNORECASE,
)

_CANONICAL_METRIC_IDS = {
    "p_e": "RT_VALUE_PE",
    "pe": "RT_VALUE_PE",
    "price_to_earning": "RT_VALUE_PE",
    "price_to_earnings": "RT_VALUE_PE",
    "trailing_eps": "RT_VALUE_EPS",
    "eps": "RT_VALUE_EPS",
    "beta": "RT_VALUE_BETA",
    "market_cap": "RT_VALUE_MARKET_CAP",
    "market_capital": "RT_VALUE_MARKET_CAP",
    "market_capitalization": "RT_VALUE_MARKET_CAP",
    "outstanding_share": "RT_VALUE_OUTSTANDING_SHARES",
    "outstanding_shares": "RT_VALUE_OUTSTANDING_SHARES",
}


def save_json(filename, data):
    """Lưu file JSON vào data/finance."""

    os.makedirs(CACHE_DIR, exist_ok=True)

    path = os.path.join(
        CACHE_DIR,
        filename,
    )

    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=CACHE_DIR,
            prefix=f".{filename}.",
            suffix=".tmp",
            delete=False,
        ) as f:
            temp_path = f.name
            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
            f.flush()
            os.fsync(f.fileno())

        os.replace(temp_path, path)

        print(
            f"💾 Saved {filename} → {path}"
        )

    except Exception as e:
        print(
            f"⚠️ Không thể lưu {filename}: {e}"
        )
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


def load_json(filename):
    """Đọc cache nếu có."""

    path = os.path.join(
        CACHE_DIR,
        filename,
    )

    if not os.path.exists(path):
        return None

    try:
        with open(
            path,
            encoding="utf-8",
        ) as f:
            return json.load(f)

    except Exception as e:
        print(
            f"⚠️ Lỗi đọc cache {filename}: {e}"
        )

        return None


def _cache_is_fresh(cached):
    """
    Kiểm tra cache còn hạn hay không.

    Đồng thời kiểm tra CACHE_VERSION để cache theo schema cũ
    tự động bị fetch lại.
    """

    if not cached:
        return False

    if cached.get("cache_version") != CACHE_VERSION:
        return False

    # Fast summary chỉ là dữ liệu tạm để UI hiện ngay. Fundamental.ratio
    # vẫn cần chạy nền để hoàn thiện EPS/Beta và các kỳ báo cáo.
    if cached.get("partial"):
        return False

    updated_at = cached.get("updated_at")

    if not updated_at:
        return False

    try:
        updated_time = datetime.strptime(
            updated_at,
            "%Y-%m-%d %H:%M:%S",
        )

        return (
            datetime.now() - updated_time
            < timedelta(
                hours=CACHE_TTL_HOURS
            )
        )

    except Exception:
        return False


def _cache_is_usable(cached):
    """Cache đúng schema có thể dùng trong lúc cập nhật nền."""
    return bool(
        cached
        and cached.get("cache_version") == CACHE_VERSION
        and isinstance(cached.get("data"), list)
        and cached.get("data")
    )


def _get_finance_lock(symbol: str):
    with _finance_locks_guard:
        lock = _finance_locks.get(symbol)

        if lock is None:
            lock = threading.Lock()
            _finance_locks[symbol] = lock

        return lock


def _pace_upstream_request():
    global _last_call

    with _request_rate_lock:
        elapsed = time.time() - _last_call

        if elapsed < FINANCE_REQUEST_DELAY_SECONDS:
            time.sleep(FINANCE_REQUEST_DELAY_SECONDS - elapsed)

        _last_call = time.time()


def _safe_value(value):
    """
    Convert dữ liệu Pandas/Numpy sang JSON-safe.

    NaN / pd.NA / inf -> None
    """

    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    # numpy scalar -> Python scalar
    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            pass

    if isinstance(value, bool):
        return value

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        if not math.isfinite(value):
            return None

        return value

    if isinstance(value, datetime):
        return value.isoformat()

    return str(value)


def _period_key(period):
    """
    Convert:
        2026-Q2 -> (2026, 2)
        2025-Q4 -> (2025, 4)

    Dùng để sort kỳ mới nhất trước.
    """

    if period is None:
        return 0, 0

    text = str(period).strip()
    text = re.sub(r"_\d+$", "", text)

    match = re.match(
        r"^(\d{4})-Q(\d)$",
        text,
        re.IGNORECASE,
    )

    if match:
        return (
            int(match.group(1)),
            int(match.group(2)),
        )

    # Trường hợp period dạng năm: 2026
    match = re.match(
        r"^(\d{4})$",
        text,
    )

    if match:
        return (
            int(match.group(1)),
            0,
        )

    return 0, 0


def _order_key(record):
    try:
        return float(
            record.get("order")
            or 999999
        )
    except Exception:
        return 999999


def _normalize_metric_key(value):
    text = str(value or "").strip()
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def _canonical_metric_id(item_id, name=""):
    normalized_id = _normalize_metric_key(item_id)

    if normalized_id in _CANONICAL_METRIC_IDS:
        return _CANONICAL_METRIC_IDS[normalized_id]

    normalized_name = _normalize_metric_key(name)

    if "market" in normalized_name and (
        "cap" in normalized_name or "capital" in normalized_name
    ):
        return "RT_VALUE_MARKET_CAP"

    if "outstanding" in normalized_name and "share" in normalized_name:
        return "RT_VALUE_OUTSTANDING_SHARES"

    if normalized_name == "beta" or normalized_name.endswith("_beta"):
        return "RT_VALUE_BETA"

    return str(item_id or "").strip()


def _normalize_period(value):
    match = _PERIOD_COLUMN_RE.match(
        str(value or "").strip()
    )
    return match.group(1).upper() if match else None


def _normalize_records(df):
    """
    Chuẩn hóa cả hai schema của vnstock_data:

    - Dạng rộng mới: item, item_id, 2026-Q1, 2025-Q4...
    - Dạng dài cũ: id/item_id, period, value...

    Output luôn là: id, source_id, name, period, unit, value, order.
    """

    records = []
    columns = [str(column) for column in df.columns]
    column_lookup = {
        column.lower(): column
        for column in columns
    }

    id_column = column_lookup.get("item_id") or column_lookup.get("id")
    name_column = column_lookup.get("item") or column_lookup.get("name")
    unit_column = column_lookup.get("unit")
    order_column = column_lookup.get("order")
    period_column = column_lookup.get("period")
    value_column = column_lookup.get("value")

    # Schema dài đã được chuẩn hóa sẵn từ một số phiên bản vnstock_data.
    if period_column and value_column:
        for row_index, (_, row) in enumerate(df.iterrows()):
            source_id = row.get(id_column) if id_column else ""
            name = row.get(name_column) if name_column else ""

            records.append({
                "id": _canonical_metric_id(source_id, name),
                "source_id": _safe_value(source_id),
                "name": _safe_value(name),
                "period": (
                    _normalize_period(row.get(period_column))
                    or _safe_value(row.get(period_column))
                ),
                "unit": _safe_value(row.get(unit_column)) if unit_column else None,
                "value": _safe_value(row.get(value_column)),
                "order": _safe_value(row.get(order_column)) if order_column else row_index,
            })

        return records

    period_columns = [
        column
        for column in columns
        if _normalize_period(column)
    ]

    for row_index, (_, row) in enumerate(df.iterrows()):
        source_id = row.get(id_column) if id_column else ""
        name = row.get(name_column) if name_column else ""
        canonical_id = _canonical_metric_id(source_id, name)

        for period_key in period_columns:
            records.append({
                "id": canonical_id,
                "source_id": _safe_value(source_id),
                "name": _safe_value(name),
                "period": _normalize_period(period_key),
                "source_period": period_key,
                "unit": _safe_value(row.get(unit_column)) if unit_column else None,
                "value": _safe_value(row.get(period_key)),
                "order": _safe_value(row.get(order_column)) if order_column else row_index,
            })


    return records


def _limit_periods(records):
    """
    Giữ MAX_PERIODS kỳ gần nhất.

    Ví dụ:
        2026-Q2
        2026-Q1
        2025-Q4
        ...
    """

    periods = {
        str(row.get("period"))
        for row in records
        if row.get("period")
    }

    sorted_periods = sorted(
        periods,
        key=_period_key,
        reverse=True,
    )

    latest_periods = sorted_periods[
        :MAX_PERIODS
    ]

    result = []

    # Đảm bảo từng period vẫn giữ đúng order metric
    for period in latest_periods:
        rows = [
            row
            for row in records
            if str(row.get("period"))
            == period
        ]

        rows.sort(
            key=_order_key
        )

        result.extend(rows)

    return result


def _fetch_from_api(
    symbol: str,
    period: str = "quarter",
):
    """
    Gọi vnstock_data Fundamental.ratio.

    Schema vnstock_data hiện tại dạng rộng:

        {
            "item": "Chỉ số giá thị trường trên thu nhập (P/E)",
            "item_id": "p_e",
            "2026-Q1": 15.92,
            "2025-Q4": 15.53
        }

    _normalize_records() chuyển bảng này về schema dài ổn định cho frontend.
    """

    symbol = symbol.strip().upper()
    _pace_upstream_request()

    try:
        print(
            f"📈 Fetching Fundamental.ratio("
            f"{symbol}, period='{period}')"
        )

        fundamental = Fundamental()

        upstream_started = time.perf_counter()

        df = (
            fundamental
            .equity(symbol)
            .ratio(
                period=period,
                lang="en",
                # Quan trọng:
                # Không drop NaN vì có thể kỳ mới EPS/Beta
                # chưa có nhưng kỳ trước có.
                dropna=False,
            )
        )

        print(
            f"⏱️ vnstock_data.ratio {symbol}: "
            f"{time.perf_counter() - upstream_started:.2f}s"
        )

        if df is None or df.empty:
            print(
                f"⚠️ Không có dữ liệu ratio "
                f"cho {symbol}"
            )

            return {}

        # Trường hợp vnstock_data trả MultiIndex column
        if isinstance(
            df.columns,
            pd.MultiIndex,
        ):
            df.columns = [
                " ".join(
                    [
                        str(c)
                        for c in col
                        if (
                            c
                            and str(c)
                            != "nan"
                        )
                    ]
                ).strip()
                for col
                in df.columns.values
            ]

        # KHÔNG dùng df.head(10)
        #
        # Schema mới mỗi metric là 1 row.
        # head(10) sẽ chỉ lấy đúng 10 metric
        # của kỳ mới nhất và mất toàn bộ kỳ trước.

        records = _normalize_records(
            df
        )

        if not records:
            print(
                f"⚠️ Schema ratio không nhận diện được cho {symbol}; "
                f"columns={list(df.columns)}"
            )
            return {}

        records = _limit_periods(
            records
        )

        if not any(
            row.get("id") == "RT_VALUE_BETA" and row.get("value") is not None
            for row in records
        ):
            beta = _calculate_beta_from_cache(symbol)

            if beta is not None:
                records.insert(0, {
                    "id": "RT_VALUE_BETA",
                    "source_id": "calculated_beta_252d",
                    "name": "Beta (252 trading days)",
                    "period": "latest",
                    "unit": None,
                    "value": beta,
                    "order": -1,
                })

        data = {
            "cache_version": CACHE_VERSION,
            "symbol": symbol,
            "period": period,
            "count": len(records),
            "data": records,
            "updated_year": datetime.now().year,
            "updated_at": (
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            ),
        }

        print(
            f"✅ Ratio {symbol}: "
            f"{len(records)} records"
        )

        return data

    except Exception as e:
        print(
            f"❌ Lỗi fetch_finance"
            f"({symbol}): {e}"
        )

        traceback.print_exc()

        return {}


def _refresh_finance(symbol, period, cache_file):
    """Fetch và lưu finance; single-flight theo symbol + period."""
    lock_key = f"{symbol}:{period}"

    with _get_finance_lock(lock_key):
        cached = load_json(cache_file)

        if _cache_is_fresh(cached):
            return cached

        print(f"🔄 Cập nhật ratio mới cho {symbol}")
        data = _fetch_from_api(symbol, period)

        if data and data.get("data"):
            save_json(cache_file, data)
            return data

        if cached:
            print(f"⚠️ API lỗi, fallback cache cũ của {symbol}")
            return cached

        return {}


def _fetch_fast_summary(symbol, period):
    """Lấy các metric Tổng quan nhanh từ cùng Market layer với stock fetcher."""
    symbol = symbol.strip().upper()
    _pace_upstream_request()

    try:
        started = time.perf_counter()
        df = Market().equity(symbol).summary()

        print(
            f"⏱️ vnstock_data.summary {symbol}: "
            f"{time.perf_counter() - started:.2f}s"
        )

        if df is None or df.empty:
            return {}

        row = df.iloc[-1]
        values = {
            _normalize_metric_key(column): _safe_value(row.get(column))
            for column in df.columns
        }

        aliases = {
            "RT_VALUE_PE": (
                "pe",
                "p_e",
                "ttm_pe",
                "price_to_earning",
                "price_to_earnings",
            ),
            "RT_VALUE_EPS": (
                "eps",
                "trailing_eps",
                "ttm_eps",
            ),
            "RT_VALUE_BETA": ("beta",),
            "RT_VALUE_MARKET_CAP": (
                "market_cap",
                "market_capital",
                "market_capitalization",
            ),
            "RT_VALUE_OUTSTANDING_SHARES": (
                "outstanding_share",
                "outstanding_shares",
                "shares_outstanding",
            ),
        }

        names = {
            "RT_VALUE_PE": "P/E",
            "RT_VALUE_EPS": "EPS",
            "RT_VALUE_BETA": "Beta",
            "RT_VALUE_MARKET_CAP": "Market Cap",
            "RT_VALUE_OUTSTANDING_SHARES": "Outstanding Shares",
        }

        records = []

        for order, (metric_id, source_aliases) in enumerate(aliases.items()):
            source_id = next(
                (alias for alias in source_aliases if values.get(alias) is not None),
                None,
            )

            if source_id is None:
                continue

            value = values[source_id]
            unit = None

            # Market.summary của một số source trả vốn hóa theo tỷ VND.
            if metric_id == "RT_VALUE_MARKET_CAP":
                try:
                    numeric_value = float(value)
                    if abs(numeric_value) < 1_000_000_000:
                        value = numeric_value * 1_000_000_000
                except (TypeError, ValueError):
                    pass
                unit = "VND"

            records.append({
                "id": metric_id,
                "source_id": source_id,
                "name": names[metric_id],
                "period": "latest",
                "unit": unit,
                "value": value,
                "order": order,
            })

        if not any(row["id"] == "RT_VALUE_BETA" for row in records):
            beta = _calculate_beta_from_cache(symbol)

            if beta is not None:
                records.append({
                    "id": "RT_VALUE_BETA",
                    "source_id": "calculated_beta_252d",
                    "name": "Beta (252 trading days)",
                    "period": "latest",
                    "unit": None,
                    "value": beta,
                    "order": len(records),
                })

        if not records:
            return {}

        return {
            "cache_version": CACHE_VERSION,
            "partial": True,
            "symbol": symbol,
            "period": period,
            "count": len(records),
            "data": records,
            "updated_year": datetime.now().year,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    except Exception as exc:
        print(f"⚠️ Fast finance summary {symbol} lỗi: {exc}")
        return {}


def _calculate_beta_from_cache(symbol):
    """Tính Beta từ cache OHLCV cổ phiếu và VNINDEX, không gọi thêm upstream."""
    stock_path = data_path("stocks", f"{symbol}.json")
    index_path = data_path("vnindex.json")

    if not stock_path.exists() or not index_path.exists():
        return None

    try:
        with open(stock_path, encoding="utf-8") as stock_file:
            stock_rows = json.load(stock_file)

        with open(index_path, encoding="utf-8") as index_file:
            index_rows = json.load(index_file)

        stock_close = {
            str(row.get("time", ""))[:10]: _safe_value(row.get("close"))
            for row in stock_rows
            if row.get("time") and row.get("close") is not None
        }
        index_close = {
            str(row.get("time", ""))[:10]: _safe_value(row.get("close"))
            for row in index_rows
            if row.get("time") and row.get("close") is not None
        }

        common_dates = sorted(set(stock_close) & set(index_close))[-253:]

        if len(common_dates) < 31:
            return None

        prices = pd.DataFrame({
            "stock": [float(stock_close[date]) for date in common_dates],
            "market": [float(index_close[date]) for date in common_dates],
        })
        returns = prices.pct_change(fill_method=None).dropna()

        if len(returns) < 30:
            return None

        market_variance = returns["market"].var()

        if not market_variance or not math.isfinite(market_variance):
            return None

        beta = returns["stock"].cov(returns["market"]) / market_variance
        return round(float(beta), 4) if math.isfinite(beta) else None
    except Exception as exc:
        print(f"⚠️ Không tính được Beta cache cho {symbol}: {exc}")
        return None


def _enrich_beta(data, symbol):
    """Bổ sung Beta cho cả cache Finance đã tạo từ trước."""
    if not data or not isinstance(data.get("data"), list):
        return data

    if any(
        row.get("id") == "RT_VALUE_BETA" and row.get("value") is not None
        for row in data["data"]
    ):
        return data

    beta = _calculate_beta_from_cache(symbol)

    if beta is None:
        return data

    data["data"].insert(0, {
        "id": "RT_VALUE_BETA",
        "source_id": "calculated_beta_252d",
        "name": "Beta (252 trading days)",
        "period": "latest",
        "unit": None,
        "value": beta,
        "order": -1,
    })
    data["count"] = len(data["data"])
    return data


def _start_finance_refresh(symbol, period, cache_file):
    """Khởi động tối đa một refresh nền cho mỗi symbol + period."""
    flight_key = f"{symbol}:{period}"

    with _finance_flights_guard:
        if flight_key in _finance_flights:
            print(f"⏳ Ratio {symbol} đang refresh nền")
            return

        _finance_flights.add(flight_key)

    def run():
        try:
            _refresh_finance(symbol, period, cache_file)
        finally:
            with _finance_flights_guard:
                _finance_flights.discard(flight_key)

    threading.Thread(
        target=run,
        name=f"finance-refresh-{symbol}-{period}",
        daemon=True,
    ).start()


def fetch_finance(
    symbol: str,
    period: str = "quarter",
):
    """
    Lấy financial ratios bằng stale-while-revalidate.

    Cache đúng schema được trả ngay; nếu hết TTL thì refresh chạy nền.
    Chỉ mã chưa từng có cache mới phải đợi vnstock_data ở request đầu tiên.
    """
    symbol = symbol.strip().upper()

    if not symbol:
        return {}

    cache_file = f"{symbol}_ratio_{period}.json"
    cached = load_json(cache_file)
    cached = _enrich_beta(cached, symbol)

    if _cache_is_fresh(cached):
        return cached

    if _cache_is_usable(cached):
        _start_finance_refresh(symbol, period, cache_file)
        return cached

    fast_data = _fetch_fast_summary(symbol, period)

    if fast_data and fast_data.get("data"):
        save_json(cache_file, fast_data)
        _start_finance_refresh(symbol, period, cache_file)
        return fast_data

    return _refresh_finance(symbol, period, cache_file)
