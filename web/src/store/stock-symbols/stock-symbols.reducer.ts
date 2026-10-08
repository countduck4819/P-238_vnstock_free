import { createSlice } from "@reduxjs/toolkit";
import {
    fetchStockCandleData,
    fetchStockSymbols,
    fetchStocks,
} from "./stock-symbols.api";
import { StockIndex } from "@/share/enum";
import { STOCK_INDEX_MAP } from "@/share/const/const";

export interface Candle {
    time: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
}

interface StockItem {
    symbol: string;
    org_name: string;
}

interface StockSymbolsState {
    symbolsList: string[];
    stocksFullList: StockItem[];
    stocksSymbolList: string[];
    candleData: Candle[];
    loading: boolean;
    error: string | null;
}

const initialState: StockSymbolsState = {
    symbolsList: [],
    stocksFullList: [],
    stocksSymbolList: [],
    candleData: [],
    loading: false,
    error: null,
};

export const stockSymbolsSlice = createSlice({
    name: "stockSymbolsSlice",
    initialState,
    reducers: {
        clearStockSymbols: (state) => {
            state.symbolsList = [];
            state.stocksFullList = [];
            state.stocksSymbolList = [];
            state.candleData = [];
            state.error = null;
        },
    },
    extraReducers: (builder) => {
        builder
            .addCase(fetchStockSymbols.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(fetchStockSymbols.fulfilled, (state, action) => {
                state.loading = false;
                state.symbolsList = action.payload.map((item: any) =>
                    typeof item === "string" ? item : item.symbol,
                );
            })
            .addCase(fetchStockSymbols.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload as string;
            });

        builder
            .addCase(fetchStocks.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(fetchStocks.fulfilled, (state, action) => {
                state.loading = false;
                const data = action.payload || [];

                const defaultIndices = Object.entries(STOCK_INDEX_MAP).map(
                    ([symbol, org_name]) => ({
                        symbol: symbol.toUpperCase().trim(),
                        org_name,
                    }),
                );

                // Khử trùng lặp theo symbol và ưu tiên bản ghi có org_name đầy đủ
                const stockMap = new Map<string, StockItem>();

                // Thêm các chỉ số cơ sở trước (VNINDEX, HNXINDEX, UPCOMINDEX)
                for (const idx of defaultIndices) {
                    stockMap.set(idx.symbol, idx);
                }

                // Thêm danh sách cổ phiếu từ API
                for (const item of data) {
                    if (!item?.symbol) continue;
                    const sym = String(item.symbol).toUpperCase().trim();
                    const name = String(item.org_name || item.organ_name || "").trim();
                    const existing = stockMap.get(sym);

                    if (
                        !existing ||
                        (!existing.org_name && name) ||
                        (existing.org_name === sym && name && name !== sym)
                    ) {
                        stockMap.set(sym, {
                            symbol: sym,
                            org_name: name || sym,
                        });
                    }
                }

                const finalData = Array.from(stockMap.values());
                state.stocksFullList = finalData;
                state.stocksSymbolList = finalData.map((item) => item.symbol);
            })
            .addCase(fetchStocks.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload as string;
            });

        builder
            .addCase(fetchStockCandleData.pending, (state) => {
                state.loading = true;
                state.error = null;
                state.candleData = [];
            })
            .addCase(fetchStockCandleData.fulfilled, (state, action) => {
                state.loading = false;
                state.candleData = action.payload;
            })
            .addCase(fetchStockCandleData.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload as string;
            });
    },
});

export const { clearStockSymbols } = stockSymbolsSlice.actions;
export default stockSymbolsSlice.reducer;
