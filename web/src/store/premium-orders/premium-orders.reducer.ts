import { createSlice } from "@reduxjs/toolkit";
import {
    fetchPremiumOrdersQuery,
    updatePremiumOrder,
    deletePremiumOrder,
} from "./premium-orders.api";

export enum PremiumOrderStatus {
    PENDING = "PENDING",
    PAID = "PAID",
    CANCEL = "CANCEL",
}

export interface PremiumOrder {
    id: number;
    orderCode: string;
    userId: number;
    user?: {
        username: string;
        fullName?: string;
    };
    amount: number;
    status: PremiumOrderStatus;
    paymentMethod?: string;
    transactionId?: string;
    createdAt?: string;
}

const initialState = {
    list: [] as PremiumOrder[],
    loading: false,
    error: null as string | null,
    meta: null as any,
};

export const premiumOrdersSlice = createSlice({
    name: "premiumOrders",
    initialState,
    reducers: {},
    extraReducers: (builder) => {
        builder
            .addCase(fetchPremiumOrdersQuery.pending, (state) => {
                state.loading = true;
            })
            .addCase(fetchPremiumOrdersQuery.fulfilled, (state, action) => {
                state.loading = false;
                state.list = action.payload.data;
                state.meta = action.payload.meta;
            })
            .addCase(updatePremiumOrder.fulfilled, (state, action) => {
                const updated = action.payload;
                state.list = state.list.map((o) =>
                    o.id === updated.id ? updated : o
                );
            })
            .addCase(deletePremiumOrder.fulfilled, (state, action) => {
                const id = action.payload;
                state.list = state.list.filter((o) => o.id !== id);
            });
    },
});

export default premiumOrdersSlice.reducer;
