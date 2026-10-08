import { createSlice } from "@reduxjs/toolkit";
import {
    createStockRec,
    deleteStockRec,
    fetchStockRecDetail,
    fetchStockRecsQuery,
    updateStockRec,
} from "./stock-recommendations.api";

export enum StockRecStatus {
    ACTIVE = "ACTIVE",
    TARGET_HIT = "TARGET_HIT",
    STOP_LOSS = "STOP_LOSS",
    CLOSED = "CLOSED",
}

export interface StockRecommendation {
    id: string;
    stockId: number;
    stock?: {
        code: string;
        name: string;
    };
    buyPrice: number;
    targetPrice: number;
    stopLossPrice: number;
    status: StockRecStatus;
    note?: string;
    closedAt?: string | null;
}

interface Meta {
    page?: number;
    limit?: number;
    total?: number;
    totalPages?: number;
}

interface StockRecommendationState {
    list: StockRecommendation[];
    selected: StockRecommendation | null;
    loading: boolean;
    error: string | null;
    meta: Meta | null;
}

const initialState: StockRecommendationState = {
    list: [],
    selected: null,
    loading: false,
    error: null,
    meta: null,
};

export const stockRecommendationsSlice = createSlice({
    name: "stockRecommendationsSlice",
    initialState,
    reducers: {
        clearSelected: (state) => {
            state.selected = null;
        },
    },
    extraReducers: (builder) => {
        builder
            .addCase(fetchStockRecsQuery.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(fetchStockRecsQuery.fulfilled, (state, action) => {
                state.loading = false;
                state.list = action.payload.data || [];
                state.meta = action.payload.meta || null;
            })
            .addCase(fetchStockRecsQuery.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload as string;
            });

        builder.addCase(fetchStockRecDetail.fulfilled, (state, action) => {
            state.selected = action.payload;
        });

        builder.addCase(createStockRec.fulfilled, (state, action) => {
            state.list.unshift(action.payload);
        });

        builder.addCase(updateStockRec.fulfilled, (state, action) => {
            const updated = action.payload;
            state.list = state.list.map((item) =>
                item.id === updated.id ? updated : item
            );
        });

        builder.addCase(deleteStockRec.fulfilled, (state, action) => {
            state.list = state.list.filter((i) => i.id !== action.payload);
        });
    },
});

export const { clearSelected } = stockRecommendationsSlice.actions;
export default stockRecommendationsSlice.reducer;
