from __future__ import annotations

import json
import math
import os
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
try:
    from vnstock_data import Market
except ImportError:
    from vnstock import Market

from core.paths import data_path


VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

HISTORY_START = "2015-01-01"
UPDATE_HOUR = 17

REQUEST_DELAY = 0.5
CACHE_DIR = data_path("stocks")

_last_call = 0.0
_api_lock = threading.Lock()


def save_json(filename: str, data: list[dict]) -> None:
    """Lưu cache OHLCV vào data/stocks."""
    os.makedirs(CACHE_DIR, exist_ok=True)

    path = os.path.join(CACHE_DIR, filename)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )

    print(f"💾 Saved {filename} → {path}")


def load_json(filename: str):
    """Đọc cache JSON nếu tồn tại."""
    path = os.path.join(CACHE_DIR, filename)

    if not os.path.exists(path):
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            return None

        return data

    except Exception as exc:
        print(f"⚠️ Không đọc được cache {filename}: {exc}")
        return None


def _is_valid_number(value) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _fetch_from_api(
    symbol: str,
    start: str,
    end: str,
) -> list[dict]:
    """
    Lấy dữ liệu trực tiếp từ vnstock_data.

    Các request được serialize để hạn chế nhiều request đồng thời
    cùng đập vào upstream.
    """
    global _last_call

    with _api_lock:
        now = time.time()

        elapsed = now - _last_call

        if elapsed < REQUEST_DELAY:
            wait_time = REQUEST_DELAY - elapsed

            print(
                f"⏸️ Chờ {wait_time:.2f}s "
                "để kiểm soát tần suất request..."
            )

            time.sleep(wait_time)

        _last_call = time.time()

        print(
            f"📈 Fetching từ vnstock_data: "
            f"{symbol} ({start} → {end})"
        )

        start_dt = pd.to_datetime(start)
        end_dt = pd.to_datetime(end)

        try:
            market = Market()
            df = market.equity(symbol).ohlcv(
                start=start_dt.strftime("%Y-%m-%d"),
                end=end_dt.strftime("%Y-%m-%d"),
                interval="1D",
            )
        except Exception as exc:
            print(f"⚠️ Lỗi fetch từ vnstock_data cho {symbol}: {exc}")
            df = None

    if df is None or df.empty:
        print(f"⚠️ API trả rỗng cho {symbol}")
        return []

    data: list[dict] = []

    for _, row in df.iterrows():
        try:
            ts = (
                row["time"].strftime("%Y-%m-%d")
                if hasattr(row["time"], "strftime")
                else str(row["time"])[:10]
            )

            open_price = float(row["open"])
            high_price = float(row["high"])
            low_price = float(row["low"])
            close_price = float(row["close"])

            # Không cho NaN/Infinity lọt vào cache.
            if not all(
                [
                    _is_valid_number(open_price),
                    _is_valid_number(high_price),
                    _is_valid_number(low_price),
                    _is_valid_number(close_price),
                ]
            ):
                print(
                    f"⚠️ Bỏ qua {symbol} ngày {ts}: "
                    "OHLC chưa hoàn chỉnh."
                )
                continue

            volume_raw = row.get("volume", 0)

            if _is_valid_number(volume_raw):
                volume = int(float(volume_raw))
            else:
                volume = 0

            data.append(
                {
                    "time": ts,
                    "open": open_price,
                    "high": high_price,
                    "low": low_price,
                    "close": close_price,
                    "volume": volume,
                }
            )

        except Exception as exc:
            print(f"⚠️ Lỗi dòng dữ liệu {symbol}: {exc}")
            continue

    return data


def _previous_weekday(date_value):
    """Lùi về ngày làm việc gần nhất."""
    result = date_value - timedelta(days=1)

    while result.weekday() >= 5:
        result -= timedelta(days=1)

    return result


def get_target_trading_day() -> str:
    """
    Ngày tối đa mà cache được phép cập nhật.

    Mon-Fri trước 17h VN:
        phiên làm việc trước đó.

    Mon-Fri từ 17h VN:
        hôm nay.

    Sat/Sun:
        thứ Sáu gần nhất.
    """
    now = datetime.now(VN_TZ)
    today = now.date()
    weekday = today.weekday()

    # Thứ 7
    if weekday == 5:
        return (today - timedelta(days=1)).strftime("%Y-%m-%d")

    # Chủ nhật
    if weekday == 6:
        return (today - timedelta(days=2)).strftime("%Y-%m-%d")

    # Thứ 2 - Thứ 6 nhưng chưa tới 17h:
    # chỉ dùng phiên đã đóng trước đó.
    if now.hour < UPDATE_HOUR:
        return _previous_weekday(today).strftime("%Y-%m-%d")

    # Sau 17h ngày làm việc:
    # cho phép lấy dữ liệu hôm nay.
    return today.strftime("%Y-%m-%d")


def merge_data(
    cached_data: list[dict] | None,
    new_data: list[dict],
) -> list[dict]:
    """
    Merge theo ngày.

    Data mới chỉ thay thế đúng ngày trùng nhau,
    tuyệt đối không xóa toàn bộ lịch sử cache.
    """
    merged: dict[str, dict] = {}

    for item in cached_data or []:
        date = item.get("time")

        if date:
            merged[date] = item

    for item in new_data:
        date = item.get("time")

        if date:
            merged[date] = item

    return sorted(
        merged.values(),
        key=lambda item: item["time"],
    )


def filter_requested_range(
    data: list[dict],
    start: str,
    end: str,
) -> list[dict]:
    """Chỉ lọc response, không làm thay đổi cache."""
    return [
        item
        for item in data
        if start <= item.get("time", "") <= end
    ]


def fetch_stock(
    symbol: str,
    start: str,
    end: str,
):
    symbol = symbol.upper().strip()

    cache_file = f"{symbol}.json"

    cached_data = load_json(cache_file)

    target_trading_day = get_target_trading_day()

    # Không cho frontend yêu cầu dữ liệu vượt quá phiên
    # mà hệ thống cho phép cache.
    effective_end = min(end, target_trading_day)

    print(
        f"🕒 {symbol}: target trading day = "
        f"{target_trading_day}"
    )

    #
    # 1. CHƯA CÓ CACHE
    #
    # Trường hợp bootstrap ban đầu:
    # lấy toàn bộ lịch sử đến phiên đã đóng gần nhất.
    #
    if not cached_data:
        print(
            f"🆕 Không có cache {symbol} "
            "→ tải lịch sử ban đầu."
        )

        data = _fetch_from_api(
            symbol,
            HISTORY_START,
            effective_end,
        )

        if not data:
            print(f"⚠️ Không lấy được dữ liệu {symbol}.")
            return []

        save_json(
            cache_file,
            data,
        )

        return filter_requested_range(
            data,
            start,
            effective_end,
        )

    #
    # 2. CACHE ĐÃ CÓ
    #
    cached_data = sorted(
        cached_data,
        key=lambda item: item.get("time", ""),
    )

    first_cached_date = cached_data[0]["time"]
    last_cached_date = cached_data[-1]["time"]

    print(
        f"📦 Cache {symbol}: "
        f"{first_cached_date} → {last_cached_date}"
    )

    #
    # 3. CACHE ĐÃ ĐỦ
    #
    if last_cached_date >= target_trading_day:
        print(
            f"✅ Cache {symbol} đã đủ đến "
            f"{target_trading_day} → KHÔNG fetch."
        )

        return filter_requested_range(
            cached_data,
            start,
            effective_end,
        )

    #
    # 4. CACHE THIẾU PHIÊN
    #
    # Fetch từ ngày sau ngày cuối cache.
    #
    last_date = datetime.strptime(
        last_cached_date,
        "%Y-%m-%d",
    ).date()

    update_start = (
        last_date + timedelta(days=1)
    ).strftime("%Y-%m-%d")

    print(
        f"📉 Cache {symbol} thiếu dữ liệu: "
        f"{update_start} → {target_trading_day}"
    )

    new_data = _fetch_from_api(
        symbol,
        update_start,
        target_trading_day,
    )

    if not new_data:
        print(
            f"⚠️ Không có dữ liệu mới cho {symbol} "
            "→ giữ cache hiện tại."
        )

        return filter_requested_range(
            cached_data,
            start,
            effective_end,
        )

    #
    # 5. MERGE, KHÔNG OVERWRITE
    #
    merged_data = merge_data(
        cached_data,
        new_data,
    )

    save_json(
        cache_file,
        merged_data,
    )

    print(
        f"✅ Đã cập nhật {symbol}: "
        f"{len(cached_data)} → "
        f"{len(merged_data)} records."
    )

    return filter_requested_range(
        merged_data,
        start,
        effective_end,
    )
