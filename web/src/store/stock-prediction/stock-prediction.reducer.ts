import { createSlice } from "@reduxjs/toolkit";
import { fetchStockPredictionQuery } from "./stock-prediction.api";

const predictionSlice = createSlice({
    name: "stockPrediction",
    initialState: {
        list: [] as any[],
        meta: {} as any,
        loading: false,
        error: null as string | null,
    },
    reducers: {
        clearPredictions: (state) => {
            state.list = [];
            state.meta = {};
            state.loading = false;
            state.error = null;
        },
    },
    extraReducers: (builder) => {
        builder
            .addCase(fetchStockPredictionQuery.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(fetchStockPredictionQuery.fulfilled, (state, action) => {
                state.loading = false;
                state.list = action.payload.data;
                state.meta = action.payload.meta;
            })
            .addCase(fetchStockPredictionQuery.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload as string;
            });
    },
});

export const { clearPredictions } = predictionSlice.actions;
export default predictionSlice.reducer;
