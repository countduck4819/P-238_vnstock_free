try:
    from vnstock_data import Reference
except ImportError:
    from vnstock import Reference
import traceback


def fetch_listing():
    """Lấy danh sách mã chứng khoán"""
    try:
        ref = Reference()
        df = ref.equity.list()

        data = df.to_dict(orient="records")

        print(f"📈 Fetched {len(data)} mã chứng khoán")
        return data

    except Exception as e:
        print("❌ Lỗi fetch Listing:", e)
        traceback.print_exc()
        return []
