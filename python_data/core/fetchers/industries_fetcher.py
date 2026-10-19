import traceback

from core import vnstock_client


def fetch_industries():
    """Lấy danh sách ngành nghề ICB"""
    try:
        industries = vnstock_client.industry_names()

        print(f"🏭 Fetched {len(industries)} ngành nghề")
        return industries

    except Exception as e:
        print("❌ Lỗi fetch Industries:", e)
        traceback.print_exc()
        return []
