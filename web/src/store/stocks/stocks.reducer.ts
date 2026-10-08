import { createSlice } from "@reduxjs/toolkit";
import { fetchStocksQuery } from "./stocks.api";

const stocksSlice = createSlice({
    name: "stocks",
    initialState: {
        list: [] as any[],
        meta: {} as any,
        loading: false,
        error: null as string | null,
    },
    reducers: {
        clearStocks: (state) => {
            state.list = [];
            state.meta = {};
            state.loading = false;
            state.error = null;
        },
    },
    extraReducers: (builder) => {
        builder
            .addCase(fetchStocksQuery.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(fetchStocksQuery.fulfilled, (state, action) => {
                state.loading = false;
                state.list = action.payload.data;
                state.meta = action.payload.meta;
            })
            .addCase(fetchStocksQuery.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload as string;
            });
    },
});

export const { clearStocks } = stocksSlice.actions;
export default stocksSlice.reducer;
