import traceback
from datetime import datetime, timedelta

try:
    from vnstock_data import Market
except ImportError:
    from vnstock import Market


def fetch_vnindex():
    try:
        market = Market()
        end = datetime.today()
        start = end - timedelta(days=730)

        df = market.index("VNINDEX").ohlcv(
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            interval="1D",
        )

        data = [
            {
                "time": (
                    row["time"].isoformat()
                    if hasattr(row["time"], "isoformat")
                    else row["time"]
                ),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            }
            for _, row in df.iterrows()
        ]

        print(f"📊 Fetched {len(data)} phiên VNINDEX")
        return data

    except Exception as e:
        print("❌ Lỗi fetch VNINDEX:", e)
        traceback.print_exc()
        return []
