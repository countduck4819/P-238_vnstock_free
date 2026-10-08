import { api } from "@/utils/axiosInstance";
import { createAsyncThunk } from "@reduxjs/toolkit";

const prefix = "/stock-recommendations";

export const fetchStockRecsQuery = createAsyncThunk(
    `${prefix}/paginate`,
    async (
        params: {
            page?: number;
            limit?: number;
            filters?: Record<string, any>;
        },
        { rejectWithValue }
    ) => {
        try {
            const { page = 1, limit = 10, filters = {} } = params;
            const queryString = new URLSearchParams({
                page: String(page),
                limit: String(limit),
                ...Object.fromEntries(
                    Object.entries(filters).map(([k, v]) => [k, String(v)])
                ),
            }).toString();

            const res = await api.get(`${prefix}?${queryString}`);
            return {
                data: res.data.data || [],
                meta: res.data.meta || {},
            };
        } catch (err: any) {
            return rejectWithValue(
                err.response?.data?.message ||
                    "Không thể tải danh sách khuyến nghị cổ phiếu"
            );
        }
    }
);

export const fetchStockRecDetail = createAsyncThunk(
    `${prefix}/detail`,
    async (id: string, { rejectWithValue }) => {
        try {
            const res = await api.get(`${prefix}/${id}`);
            return res.data.data || res.data;
        } catch (err: any) {
            return rejectWithValue(
                err.response?.data?.message ||
                    "Không thể tải chi tiết khuyến nghị"
            );
        }
    }
);

export const createStockRec = createAsyncThunk(
    `${prefix}/create`,
    async (data: Record<string, any>, { rejectWithValue }) => {
        try {
            const res = await api.post(`${prefix}`, data);
            return res.data.data || res.data;
        } catch (err: any) {
            return rejectWithValue(
                err.response?.data?.message || "Không thể tạo khuyến nghị mới"
            );
        }
    }
);

export const updateStockRec = createAsyncThunk(
    `${prefix}/update`,
    async (
        { id, data }: { id: string; data: Record<string, any> },
        { rejectWithValue }
    ) => {
        try {
            const res = await api.put(`${prefix}/${id}`, data);
            return res.data.data || res.data;
        } catch (err: any) {
            return rejectWithValue(
                err.response?.data?.message || "Không thể cập nhật khuyến nghị"
            );
        }
    }
);

export const deleteStockRec = createAsyncThunk(
    `${prefix}/delete`,
    async (id: string, { rejectWithValue }) => {
        try {
            await api.delete(`${prefix}/${id}`);
            return id;
        } catch (err: any) {
            return rejectWithValue(
                err.response?.data?.message || "Không thể xoá khuyến nghị"
            );
        }
    }
);
