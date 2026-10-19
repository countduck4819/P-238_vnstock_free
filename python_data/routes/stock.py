import json
import os
import threading
import time
from datetime import datetime
from flask import Blueprint, jsonify, request
from core.fetchers import fetch_stock
from core.paths import data_path

stock_bp = Blueprint("stock_bp", __name__)


@stock_bp.route("/api/stock/<symbol>")
def get_stock(symbol):
    try:
        end = datetime.today()
        start_str = request.args.get("start", "2015-01-01")
        end_str = request.args.get("end", end.strftime("%Y-%m-%d"))

        data = fetch_stock(symbol.upper(), start_str, end_str)
        return jsonify(data)
    except Exception as e:
        print(f"❌ Lỗi fetch {symbol}:", e)
        return jsonify({"error": str(e)}), 500


_overview_cache = {}
_overview_last_fetch = 0.0


def _build_overview_from_candles():
    overview = {}
    stocks_dir = data_path("stocks")
    if os.path.exists(stocks_dir):
        for fname in os.listdir(stocks_dir):
            if fname.endswith(".json") and not fname.startswith("."):
                sym = fname[:-5].upper()
                try:
                    fpath = os.path.join(stocks_dir, fname)
                    with open(fpath, "r", encoding="utf-8") as f:
                        rows = json.load(f)
                    if isinstance(rows, list) and len(rows) >= 2:
                        last = rows[-1]
                        prev = rows[-2]
                        last_close = float(last.get("close", 0) or 0)
                        prev_close = float(prev.get("close", 0) or 0)
                        if last_close > 0 and prev_close > 0:
                            chg = round(
                                ((last_close - prev_close) / prev_close) * 100, 2
                            )
                            overview[sym] = {
                                "price": last_close,
                                "change": chg,
                                "volume": float(last.get("volume", 0) or 0),
                                "time": last.get("time", ""),
                            }
                except Exception:
                    continue
    return overview

def _get_cached_stock_symbols():
    symbols = []
    stocks_dir = data_path("stocks")

    if not os.path.exists(stocks_dir):
        return symbols

    for fname in os.listdir(stocks_dir):
        if fname.endswith(".json") and not fname.startswith("."):
            symbols.append(fname[:-5].upper())

    return symbols

_overview_refresh_lock = threading.Lock()
_overview_refreshing = False


def _refresh_cached_stocks():
    """Cập nhật nến của các mã đã cache, chạy nền và tuần tự để giữ quota free."""
    global _overview_refreshing

    try:
        today = datetime.today().strftime("%Y-%m-%d")

        for sym in _get_cached_stock_symbols():
            try:
                fetch_stock(sym, "2015-01-01", today)
            except Exception as exc:
                print(f"⚠️ Không cập nhật được {sym}: {exc}")
    finally:
        with _overview_refresh_lock:
            _overview_refreshing = False


def _start_overview_refresh():
    global _overview_refreshing

    with _overview_refresh_lock:
        if _overview_refreshing:
            return

        _overview_refreshing = True

    threading.Thread(
        target=_refresh_cached_stocks,
        name="stocks-overview-refresh",
        daemon=True,
    ).start()


@stock_bp.route("/api/stocks/overview")
def get_stocks_overview():
    """Giá và % thay đổi mới nhất, đọc từ kho nến đã cache."""
    global _overview_cache, _overview_last_fetch
    now = time.time()

    # Cache 15s trong bộ nhớ để trả lời tức thì trong < 1ms
    if _overview_cache and (now - _overview_last_fetch < 15):
        return jsonify(_overview_cache)

    try:
        # Cập nhật nến chạy nền: request không phải chờ hàng trăm lượt gọi vnstock.
        _start_overview_refresh()

        # 1. Quét nhanh từ kho nến chuẩn để đảm bảo trùng khớp 100% với trang chi tiết cổ phiếu
        overview = _build_overview_from_candles()

        # 2. Đảm bảo có chỉ số thị trường cơ sở (VNINDEX)
        try:
            from core.fetchers import fetch_vnindex
            if "VNINDEX" not in overview:
                vn_data = fetch_vnindex()
                if vn_data and len(vn_data) >= 2:
                    l_c = float(vn_data[-1]["close"])
                    p_c = float(vn_data[-2]["close"])
                    chg = round(((l_c - p_c) / p_c) * 100, 2)
                    overview["VNINDEX"] = {
                        "price": l_c,
                        "change": chg,
                        "volume": 0,
                        "time": vn_data[-1].get("time", ""),
                    }
        except Exception:
            pass

        if overview:
            _overview_cache = overview
            _overview_last_fetch = now
            return jsonify(overview)

        if _overview_cache:
            return jsonify(_overview_cache)

        return jsonify({})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
