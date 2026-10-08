try:
    from vnstock_data import Reference
except ImportError:
    from vnstock import Reference
import traceback


def fetch_stocks_by_industries():
    """Lấy danh sách cổ phiếu và group theo ngành ICB"""
    try:
        ref = Reference()

        # Lấy toàn bộ cổ phiếu kèm phân ngành ICB
        df_stocks = ref.equity.list_by_industry(lang="vi")

        if df_stocks is None or df_stocks.empty:
            print("Không có dữ liệu cổ phiếu.")
            return {}

        # Kiểm tra các cột cần thiết
        if "symbol" not in df_stocks.columns:
            print("Không tìm thấy cột symbol.")
            return {}

        # vnstock_data có thể dùng tên ngành khác schema vnstock cũ
        industry_column = None

        for column in [
            "icb_name3",
            "icb_name",
            "industry",
            "industry_name",
        ]:
            if column in df_stocks.columns:
                industry_column = column
                break

        if not industry_column:
            print(
                "Không tìm thấy cột ngành trong dữ liệu "
                f"vnstock_data. Columns: {df_stocks.columns.tolist()}"
            )
            return {}

        df_stocks = df_stocks[
            ["symbol", industry_column]
        ].dropna()

        grouped = (
            df_stocks
            .groupby(industry_column)["symbol"]
            .apply(list)
            .to_dict()
        )

        return grouped

    except Exception as e:
        print("Lỗi fetch stocks_by_industry:", e)
        traceback.print_exc()
        return {}
