try:
    from vnstock_data import Reference
except ImportError:
    from vnstock import Reference
import traceback


def fetch_industries_for_code():
    """Lấy danh sách mã chứng khoán kèm thông tin ngành ICB"""
    try:
        ref = Reference()
        df = ref.equity.list_by_industry()

        data = df.to_dict(orient="records")

        print(f"📈 Fetched {len(data)} mã chứng khoán")
        return data

    except Exception as e:
        print("❌ Lỗi fetch Industries For Code:", e)
        traceback.print_exc()
        return []
