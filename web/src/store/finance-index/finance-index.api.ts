import { createAsyncThunk } from "@reduxjs/toolkit";
import { pythonApiUrl } from "@/utils/pythonApi";

const prefix = "/finance";


export const fetchFinanceIndex = createAsyncThunk(
    `${prefix}/fetchFinanceIndex`,
    async (
        symbol: string,
        { rejectWithValue, signal }
    ) => {
        try {
            const normalizedSymbol = symbol
                .trim()
                .toUpperCase();

            if (!normalizedSymbol) {
                throw new Error(
                    "Mã chứng khoán không hợp lệ."
                );
            }

            const url = pythonApiUrl(
                `${prefix}/${encodeURIComponent(normalizedSymbol)}`
            );

            const res = await fetch(url, {
                method: "GET",
                headers: {
                    Accept: "application/json",
                },
                cache: "no-store",
                signal,
            });

            let data: any = null;

            try {
                data = await res.json();
            } catch {
                throw new Error(
                    `API trả dữ liệu không hợp lệ (${res.status}).`
                );
            }

            if (!res.ok) {
                throw new Error(
                    data?.error ||
                        data?.message ||
                        `Không thể tải dữ liệu tài chính cho ${normalizedSymbol}`
                );
            }

            return data;
        } catch (err: any) {
            if (signal.aborted || err?.name === "AbortError") {
                return rejectWithValue("REQUEST_ABORTED");
            }

            return rejectWithValue(
                err?.message ||
                    `Không thể tải dữ liệu tài chính cho ${symbol}`
            );
        }
    }
);
