import traceback

from core import vnstock_client


def fetch_listing():
    """Lấy danh sách mã chứng khoán"""
    try:
        df = vnstock_client.all_symbols()

        data = df.astype(object).where(df.notna(), None).to_dict(orient="records")

        print(f"📈 Fetched {len(data)} mã chứng khoán")
        return data

    except Exception as e:
        print("❌ Lỗi fetch Listing:", e)
        traceback.print_exc()
        return []
