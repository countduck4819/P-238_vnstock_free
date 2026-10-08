import {
    createAsyncThunk,
} from "@reduxjs/toolkit";

import { api } from "@/utils/axiosInstance";
import { StockIndex } from "@/share/enum";

const prefix = "/news";

export const fetchNewsQuery =
    createAsyncThunk(
        `${prefix}/fetchQuery`,
        async (
            params: {
                page?: number;
                limit?: number;
                symbol?: string;
            },
            {
                rejectWithValue,
            }
        ) => {
            try {
                const res =
                    await api.get(
                        `${prefix}`,
                        {
                            params,
                        }
                    );

                return res.data;
            } catch (err: any) {
                return rejectWithValue(
                    err.response?.data
                        ?.message ||
                        "Không thể tải danh sách tin tức"
                );
            }
        }
    );

export const fetchNewsFromJson =
    createAsyncThunk(
        `${prefix}/fetchFromJson`,
        async (
            symbol: string,
            {
                rejectWithValue,
                signal,
            }
        ) => {
            try {
                let res: Response | null = null;

                const maxAttempts = 2;

                for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
                    res = await fetch(
                        `${process.env.NEXT_PUBLIC_API_BASE_URL_PYTHON}${prefix}/${symbol}`,
                        { signal },
                    );

                    if (
                        res.status !== 503 ||
                        attempt === maxAttempts - 1
                    ) {
                        break;
                    }

                    await res.text().catch(() => "");

                    const retryAfterRaw = Number(
                        res.headers.get("Retry-After") || 5,
                    );

                    const retryAfter = Number.isFinite(
                        retryAfterRaw,
                    )
                        ? Math.min(
                              Math.max(retryAfterRaw, 1),
                              10,
                          )
                        : 5;

                    await new Promise<void>((resolve, reject) => {
                        if (signal.aborted) {
                            reject(new DOMException("Aborted", "AbortError"));
                            return;
                        }

                        const onAbort = () => {
                            clearTimeout(timer);
                            reject(new DOMException("Aborted", "AbortError"));
                        };

                        const timer = setTimeout(
                            () => {
                                signal.removeEventListener("abort", onAbort);
                                resolve();
                            },
                            retryAfter * 1000,
                        );

                        signal.addEventListener(
                            "abort",
                            onAbort,
                            { once: true },
                        );
                    });
                }

                if (!res?.ok) {
                    const errorBody = await res?.json().catch(() => null);
                    throw new Error(
                        errorBody?.error || `HTTP ${res?.status || 0}`
                    );
                }

                const data =
                    await res.json();

                return data;
            } catch (err: any) {
                if (signal.aborted || err?.name === "AbortError") {
                    return rejectWithValue("REQUEST_ABORTED");
                }

                return rejectWithValue(
                    err?.message ||
                        `Không thể đọc dữ liệu tin tức cho ${symbol}`
                );
            }
        }
    );


export const fetchNewsDetailBySlug =
    createAsyncThunk(
        `${prefix}/fetchDetailBySlug`,
        async (
            slug: string,
            {
                rejectWithValue,
            }
        ) => {
            try {
                const res =
                    await api.get(
                        `${prefix}/${slug}`
                    );

                return res.data;
            } catch (err: any) {
                return rejectWithValue(
                    err.response?.data
                        ?.message ||
                        `Không thể tải chi tiết bài viết slug: ${slug}`
                );
            }
        }
    );

export const fetchAllNewsForVNINDEX =
    createAsyncThunk(
        `${prefix}/fetchAllForVNINDEX`,
        async (
            params: {
                page?: number;
                limit?: number;
            },
            {
                rejectWithValue,
            }
        ) => {
            try {
                const res =
                    await api.get(
                        `${prefix}`,
                        {
                            params: {
                                ...params,
                                symbol:
                                    StockIndex?.VNINDEX,
                            },
                        }
                    );

                return res.data;
            } catch (err: any) {
                return rejectWithValue(
                    err.response?.data
                        ?.message ||
                        "Không thể tải tin tổng hợp cho VNINDEX"
                );
            }
        }
    );

export const fetchNewsSearchQuery =
    createAsyncThunk(
        `${prefix}/fetchSearchQuery`,
        async (
            params: {
                page?: number;
                limit?: number;
                keyword?: string;
            },
            {
                rejectWithValue,
            }
        ) => {
            try {
                const res =
                    await api.get(
                        `${prefix}/search`,
                        {
                            params,
                        }
                    );

                return res.data;
            } catch (err: any) {
                return rejectWithValue(
                    err.response?.data
                        ?.message ||
                        "Không thể tìm kiếm tin tức"
                );
            }
        }
    );
