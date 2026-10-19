import traceback

from core import vnstock_client


def fetch_industries_for_code():
    """Lấy danh sách mã chứng khoán kèm thông tin ngành ICB"""
    try:
        df = vnstock_client.symbols_by_industries()

        data = df.astype(object).where(df.notna(), None).to_dict(orient="records")

        print(f"📈 Fetched {len(data)} mã chứng khoán")
        return data

    except Exception as e:
        print("❌ Lỗi fetch Industries For Code:", e)
        traceback.print_exc()
        return []
