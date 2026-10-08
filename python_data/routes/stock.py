import json
import os
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

@stock_bp.route("/api/stocks/overview")
def get_stocks_overview():
    """Lấy dữ liệu giá và % thay đổi mới nhất trực tiếp từ nến giá chuẩn & vnstock."""
    global _overview_cache, _overview_last_fetch
    import time
    now = time.time()

    # Cache 15s trong bộ nhớ để trả lời tức thì trong < 1ms
    if _overview_cache and (now - _overview_last_fetch < 15):
        return jsonify(_overview_cache)

    try:
        today = datetime.today().strftime("%Y-%m-%d")

        for sym in _get_cached_stock_symbols():
            try:
                fetch_stock(
                    sym,
                    "2015-01-01",
                    today,
                )
            except Exception as exc:
                print(f"⚠️ Không cập nhật được {sym}: {exc}")

        # 1. Quét nhanh từ kho nến chuẩn để đảm bảo trùng khớp 100% với trang chi tiết cổ phiếu
        overview = _build_overview_from_candles()

        # 2. Thử cập nhật thêm từ vnstock live snapshot nếu có
        try:
            from vnstock import Market
            df = Market().quote.snapshot()
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    sym = str(
                        row.get("ticker")
                        or row.get("symbol")
                        or row.get("organ_code")
                        or ""
                    ).upper().strip()
                    if sym and sym not in overview:
                        price = float(
                            row.get("match_price")
                            or row.get("price")
                            or row.get("close")
                            or 0
                        )
                        change = float(
                            row.get("percent_change")
                            or row.get("change_percent")
                            or row.get("changePercent")
                            or row.get("pct_change")
                            or row.get("change")
                            or 0
                        )
                        vol = float(
                            row.get("match_volume")
                            or row.get("volume")
                            or row.get("total_volume")
                            or 0
                        )
                        overview[sym] = {
                            "price": price,
                            "change": round(change, 2),
                            "volume": vol,
                            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        }
        except Exception as snap_err:
            pass

        # 3. Đảm bảo có chỉ số thị trường cơ sở (VNINDEX, VN30, HNXINDEX, UPINDEX)
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

