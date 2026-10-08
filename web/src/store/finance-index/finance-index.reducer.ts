import { createSlice } from "@reduxjs/toolkit";

import { fetchFinanceIndex } from "./finance-index.api";

export interface FinanceRecord {
    id?: string | null;
    source_id?: string | null;
    source_period?: string | null;
    level?: number | null;
    name?: string | null;
    order?: number | null;
    period?: string | null;
    unit?: string | null;
    value?: string | number | null;

    [key: string]:
        | string
        | number
        | null
        | undefined;
}

interface FinanceState {
    symbol: string | null;
    data: FinanceRecord[];
    loading: boolean;
    error: string | null;
    period: string | null;
    updatedAt: string | null;
    partial: boolean;
}

const initialState: FinanceState = {
    symbol: null,
    data: [],
    loading: false,
    error: null,
    period: null,
    updatedAt: null,
    partial: false,
};

export const financeIndexSlice = createSlice({
    name: "financeIndexSlice",

    initialState,

    reducers: {
        clearFinanceIndex: (state) => {
            state.symbol = null;
            state.data = [];
            state.loading = false;
            state.error = null;
            state.period = null;
            state.updatedAt = null;
            state.partial = false;
        },
    },

    extraReducers: (builder) => {
        builder
            .addCase(
                fetchFinanceIndex.pending,
                (state, action) => {
                    state.loading = true;
                    state.error = null;

                    const nextSymbol = String(
                        action.meta.arg || ""
                    ).toUpperCase();

                    // Đổi mã thì bỏ dữ liệu cũ. Poll cùng mã để chờ full ratio
                    // vẫn giữ fast summary đang hiển thị, tránh card nháy dấu -.
                    if (state.symbol !== nextSymbol) {
                        state.data = [];
                        state.partial = false;
                    }

                    state.symbol = nextSymbol;
                }
            )

            .addCase(
                fetchFinanceIndex.fulfilled,
                (state, action) => {
                    state.loading = false;
                    state.error = null;

                    state.symbol =
                        action.payload?.symbol ||
                        null;

                    state.period =
                        action.payload?.period ||
                        null;

                    state.updatedAt =
                        action.payload
                            ?.updated_at ||
                        null;

                    state.partial = Boolean(
                        action.payload?.partial
                    );

                    state.data = Array.isArray(
                        action.payload?.data
                    )
                        ? action.payload.data
                        : [];
                }
            )

            .addCase(
                fetchFinanceIndex.rejected,
                (state, action) => {
                    if (action.meta.aborted) {
                        return;
                    }

                    state.loading = false;

                    state.data = [];
                    state.partial = false;

                    state.error =
                        (action.payload as string) ||
                        "Không thể tải dữ liệu tài chính.";
                }
            );
    },
});

export const {
    clearFinanceIndex,
} = financeIndexSlice.actions;

export default financeIndexSlice.reducer;
