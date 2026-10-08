import { api } from "@/utils/axiosInstance";
import { createAsyncThunk } from "@reduxjs/toolkit";

const prefix = "/stocks";
const prefix1 = "/python-api";
/** Lấy danh sách tất cả symbol dạng ["VCB:HOSE", "SSI:HOSE", ...] */
export const fetchStockSymbols = createAsyncThunk(
    `${prefix}/stock-symbols`,
    async (_, { rejectWithValue }) => {
        try {
            const res = await api.get(`${prefix}/stock-symbols`);
            return res.data.data || res.data;
        } catch (err: any) {
            return rejectWithValue(
                err.response?.data?.message ||
                    "Không thể tải danh sách mã chứng khoán"
            );
        }
    }
);

export const fetchStocks = createAsyncThunk(
    `${prefix}/listing-stock`,
    async (_, { rejectWithValue }) => {
        try {
            const res = await api.get(`${prefix}/listing-stock`);
            return res.data.data || res.data;
        } catch (err: any) {
            return rejectWithValue(
                err.response?.data?.message ||
                    "Không thể tải danh sách mã chứng khoán"
            );
        }
    }
);

export const fetchStockCandleData = createAsyncThunk(
    "stock/fetchStockCandleData",
    async (symbol: string, { rejectWithValue }) => {
        try {
            const sym = symbol.toUpperCase().trim();
            let list: any[] = [];

            // 1. Thử NestJS endpoint /api/stocks/candle/SYM
            try {
                const res = await fetch(`/api/stocks/candle/${sym}`);
                if (res.ok) {
                    const raw = await res.json();
                    const parsed = Array.isArray(raw) ? raw : (raw?.data || []);
                    if (parsed.length > 0) list = parsed;
                }
            } catch {}

            // 2. Thử Next.js proxy /api/python/stock/SYM
            if (list.length === 0) {
                try {
                    const res = await fetch(`/api/python/stock/${sym}`);
                    if (res.ok) {
                        const raw = await res.json();
                        const parsed = Array.isArray(raw) ? raw : (raw?.data || []);
                        if (parsed.length > 0) list = parsed;
                    }
                } catch {}
            }

            // 3. Thử direct Python backend port 6060
            if (list.length === 0) {
                try {
                    const pythonBase = (
                        process.env.NEXT_PUBLIC_API_BASE_URL_PYTHON ||
                        "http://localhost:6060/api"
                    ).replace(/\/$/, "");
                    const res = await fetch(`${pythonBase}/stock/${sym}`);
                    if (res.ok) {
                        const raw = await res.json();
                        const parsed = Array.isArray(raw) ? raw : (raw?.data || []);
                        if (parsed.length > 0) list = parsed;
                    }
                } catch {}
            }

            if (list.length === 0) {
                throw new Error("Không có dữ liệu nến cho mã " + sym);
            }

            const data = list.map((d: any) => ({
                time: (d.date || d.time || "").slice(0, 10),
                open: +d.open,
                high: +d.high,
                low: +d.low,
                close: +d.close,
                volume: +d.volume || 0,
            }));

            return data;
        } catch {
            return rejectWithValue("Không thể tải dữ liệu biểu đồ");
        }
    }
);
