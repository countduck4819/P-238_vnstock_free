try:
    from vnstock_data import Reference
except ImportError:
    from vnstock import Reference
import traceback


def fetch_industries():
    """Lấy danh sách ngành nghề ICB"""
    try:
        reference = Reference()
        df = reference.industry.list(lang="vi")

        industries = sorted(
            df["icb_name"].dropna().unique().tolist()
        )

        print(f"🏭 Fetched {len(industries)} ngành nghề")
        return industries

    except Exception as e:
        print("❌ Lỗi fetch Industries:", e)
        traceback.print_exc()
        return []
