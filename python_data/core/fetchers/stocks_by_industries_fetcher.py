import traceback

from core import vnstock_client


def fetch_stocks_by_industries():
    """Lấy danh sách cổ phiếu và group theo ngành ICB"""
    try:
        # Lấy toàn bộ cổ phiếu kèm phân ngành ICB
        df_stocks = vnstock_client.symbols_by_industries()

        if df_stocks is None or df_stocks.empty:
            print("Không có dữ liệu cổ phiếu.")
            return {}

        # Kiểm tra các cột cần thiết
        if "symbol" not in df_stocks.columns:
            print("Không tìm thấy cột symbol.")
            return {}

        # Ưu tiên ICB cấp 3, các tên cột khác để phòng nguồn đổi schema
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
                f"vnstock. Columns: {df_stocks.columns.tolist()}"
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
