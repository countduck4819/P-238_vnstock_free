import { createSlice } from "@reduxjs/toolkit";

import {
    fetchNewsQuery,
    fetchNewsFromJson,
    fetchNewsDetailBySlug,
    fetchAllNewsForVNINDEX,
    fetchNewsSearchQuery,
} from "./news.api";


const newsSlice = createSlice({
    name: "news",

    initialState: {
        // Mã cổ phiếu hiện tại
        currentSymbol: "",

        // News theo mã cổ phiếu
        list: [] as any[],
        meta: {} as any,

        // VNINDEX
        vnindexList: [] as any[],
        vnindexMeta: {} as any,

        // Data từ Python
        jsonData: [] as any[],

        detail: null as any,

        searchList: [] as any[],
        searchMeta: {} as any,

        loading: false,

        error: null as string | null,
    },

    reducers: {
        clearNews: (state) => {
            state.currentSymbol = "";

            state.list = [];
            state.meta = {};

            state.vnindexList = [];
            state.vnindexMeta = {};

            state.jsonData = [];

            state.detail = null;

            state.searchList = [];
            state.searchMeta = {};

            state.loading = false;
            state.error = null;
        },
    },

    extraReducers: (builder) => {
        // =================================================
        // NEWS BY SYMBOL
        // =================================================

        builder
            .addCase(
                fetchNewsQuery.pending,
                (state, action) => {
                    const page =
                        action.meta.arg?.page || 1;

                    const symbol =
                        action.meta.arg?.symbol
                            ?.toUpperCase()
                            .trim() || "";

                    // Chỉ page 1 mới được xem là
                    // bắt đầu load một mã mới.
                    if (page === 1) {
                        if (symbol) {
                            state.currentSymbol =
                                symbol;
                        }

                        state.list = [];
                        state.meta = {};
                    }

                    state.loading = true;
                    state.error = null;
                },
            )

            .addCase(
                fetchNewsQuery.fulfilled,
                (state, action) => {
                    const page =
                        action.meta.arg?.page || 1;

                    const symbol =
                        action.meta.arg?.symbol
                            ?.toUpperCase()
                            .trim() || "";

                    // Ví dụ:
                    // đang ở CII
                    // nhưng response LDG page 2 về muộn
                    // => bỏ response LDG.
                    if (
                        symbol &&
                        state.currentSymbol &&
                        symbol !==
                            state.currentSymbol
                    ) {
                        return;
                    }

                    state.loading = false;

                    const newData =
                        action.payload?.data || [];

                    const meta =
                        action.payload?.meta || {};

                    if (page > 1) {
                        const existingIds =
                            new Set(
                                state.list.map(
                                    (item: any) =>
                                        item.news_id,
                                ),
                            );

                        const uniqueNewData =
                            newData.filter(
                                (item: any) =>
                                    !existingIds.has(
                                        item.news_id,
                                    ),
                            );

                        state.list = [
                            ...state.list,
                            ...uniqueNewData,
                        ];
                    } else {
                        state.list = newData;
                    }

                    state.meta = meta;
                },
            )

            .addCase(
                fetchNewsQuery.rejected,
                (state, action) => {
                    const symbol =
                        action.meta.arg?.symbol
                            ?.toUpperCase()
                            .trim() || "";

                    // Request mã cũ lỗi sau khi
                    // đã chuyển mã thì bỏ qua.
                    if (
                        symbol &&
                        state.currentSymbol &&
                        symbol !==
                            state.currentSymbol
                    ) {
                        return;
                    }

                    state.loading = false;

                    state.error =
                        action.payload as string;
                },
            );


        // =================================================
        // VNINDEX
        // =================================================

        builder
            .addCase(
                fetchAllNewsForVNINDEX.pending,
                (state, action) => {
                    state.loading = true;
                    state.error = null;

                    const page =
                        action.meta.arg?.page || 1;

                    if (page === 1) {
                        state.vnindexList = [];
                        state.vnindexMeta = {};
                    }
                },
            )

            .addCase(
                fetchAllNewsForVNINDEX.fulfilled,
                (state, action) => {
                    state.loading = false;

                    const newData =
                        action.payload?.data || [];

                    const meta =
                        action.payload?.meta || {};

                    const page =
                        action.meta.arg?.page || 1;

                    if (page > 1) {
                        const existingIds =
                            new Set(
                                state.vnindexList.map(
                                    (item: any) =>
                                        item.news_id,
                                ),
                            );

                        const uniqueNewData =
                            newData.filter(
                                (item: any) =>
                                    !existingIds.has(
                                        item.news_id,
                                    ),
                            );

                        state.vnindexList = [
                            ...state.vnindexList,
                            ...uniqueNewData,
                        ];
                    } else {
                        state.vnindexList =
                            newData;
                    }

                    state.vnindexMeta =
                        meta;
                },
            )

            .addCase(
                fetchAllNewsForVNINDEX.rejected,
                (state, action) => {
                    state.loading = false;

                    state.error =
                        action.payload as string;
                },
            );


        // =================================================
        // PYTHON JSON
        // =================================================

        builder
            .addCase(
                fetchNewsFromJson.pending,
                (state, action) => {
                    const symbol =
                        action.meta.arg
                            .toUpperCase()
                            .trim();

                    // Đánh dấu mã mới ngay lập tức.
                    state.currentSymbol =
                        symbol;

                    // Danh sách DB được fetch song song. Không xóa list/meta ở
                    // request refresh Python, nếu không timeout nền sẽ che mất
                    // dữ liệu NestJS đã tải được.
                    state.jsonData = [];

                    state.loading = true;
                    state.error = null;
                },
            )

            .addCase(
                fetchNewsFromJson.fulfilled,
                (state, action) => {
                    const symbol =
                        action.meta.arg
                            .toUpperCase()
                            .trim();

                    // Ví dụ:
                    //
                    // request LDG đang chạy
                    // user chuyển sang CII
                    // response LDG mới về
                    //
                    // => TUYỆT ĐỐI không ghi data LDG
                    // vào state của CII.
                    if (
                        state.currentSymbol !==
                        symbol
                    ) {
                        return;
                    }

                    state.loading = false;

                    state.jsonData =
                        action.payload?.data || [];
                },
            )

            .addCase(
                fetchNewsFromJson.rejected,
                (state, action) => {
                    if (action.meta.aborted) {
                        return;
                    }

                    const symbol =
                        action.meta.arg
                            .toUpperCase()
                            .trim();

                    // Lỗi của request mã cũ
                    // không được ảnh hưởng mã hiện tại.
                    if (
                        state.currentSymbol !==
                        symbol
                    ) {
                        return;
                    }

                    state.loading = false;

                    // Python chỉ refresh cache nền. Nếu DB đã có bài thì giữ
                    // danh sách và không biến timeout upstream thành lỗi UI.
                    state.error = state.list.length
                        ? null
                        : action.payload as string;
                },
            );


        // =================================================
        // DETAIL
        // =================================================

        builder
            .addCase(
                fetchNewsDetailBySlug.pending,
                (state) => {
                    state.loading = true;
                    state.error = null;
                },
            )

            .addCase(
                fetchNewsDetailBySlug.fulfilled,
                (state, action) => {
                    state.loading = false;

                    state.detail =
                        action.payload?.data ||
                        null;
                },
            )

            .addCase(
                fetchNewsDetailBySlug.rejected,
                (state, action) => {
                    state.loading = false;

                    state.error =
                        action.payload as string;
                },
            );


        // =================================================
        // SEARCH
        // =================================================

        builder
            .addCase(
                fetchNewsSearchQuery.pending,
                (state) => {
                    state.loading = true;
                    state.error = null;
                },
            )

            .addCase(
                fetchNewsSearchQuery.fulfilled,
                (state, action) => {
                    state.loading = false;

                    state.searchList =
                        action.payload?.data || [];

                    state.searchMeta =
                        action.payload?.meta || {};
                },
            )

            .addCase(
                fetchNewsSearchQuery.rejected,
                (state, action) => {
                    state.loading = false;

                    state.error =
                        action.payload as string;
                },
            );
    },
});


export const {
    clearNews,
} = newsSlice.actions;

export default newsSlice.reducer;
