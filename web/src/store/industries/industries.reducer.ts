import { createSlice } from "@reduxjs/toolkit";
import { fetchIndustriesQuery } from "./industries.api";

const industriesSlice = createSlice({
    name: "industries",
    initialState: {
        list: [] as any[],
        meta: {} as any,
        loading: false,
        error: null as string | null,
    },
    reducers: {
        clearIndustries: (state) => {
            state.list = [];
            state.meta = {};
            state.loading = false;
            state.error = null;
        },
    },
    extraReducers: (builder) => {
        builder
            .addCase(fetchIndustriesQuery.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(fetchIndustriesQuery.fulfilled, (state, action) => {
                state.loading = false;
                state.list = action.payload.data;
                state.meta = action.payload.meta;
            })
            .addCase(fetchIndustriesQuery.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload as string;
            });
    },
});

export const { clearIndustries } = industriesSlice.actions;
export default industriesSlice.reducer;
