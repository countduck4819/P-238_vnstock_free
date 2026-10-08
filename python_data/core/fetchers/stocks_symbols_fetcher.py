try:
    from vnstock_data import Reference
except ImportError:
    from vnstock import Reference
import traceback
import pandas as pd


def fetch_stocks_symbols():
    """
    Lấy toàn bộ mã cổ phiếu đang niêm yết kèm sàn (format EXCHANGE:SYMBOL)
    Dữ liệu này dùng để feed cho TradingView widget.
    """
    try:
        ref = Reference()

        # Lấy toàn bộ mã cổ phiếu
        df_all = ref.equity.list()
        valid_symbols = set(
            df_all["symbol"].dropna().unique()
        )

        # Lấy danh sách cổ phiếu theo sàn
        df_exchange = ref.equity.list_by_exchange()
        df_exchange = df_exchange[
            ["symbol", "exchange"]
        ].dropna()

        # Chỉ giữ các mã hợp lệ
        df_filtered = df_exchange[
            df_exchange["symbol"].isin(valid_symbols)
        ].copy()

        # TradingView format: EXCHANGE:SYMBOL
        df_filtered["symbol_full"] = (
            df_filtered["exchange"]
            + ":"
            + df_filtered["symbol"]
        )

        all_symbols = sorted(
            df_filtered["symbol_full"]
            .drop_duplicates()
            .tolist()
        )

        return all_symbols

    except Exception as e:
        print(
            "Lỗi fetch_all_symbols_with_exchange:",
            e
        )
        traceback.print_exc()
        return []
