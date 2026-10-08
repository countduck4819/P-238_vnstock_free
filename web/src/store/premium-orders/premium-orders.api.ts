import { api } from "@/utils/axiosInstance";
import { createAsyncThunk } from "@reduxjs/toolkit";

const prefix = "/premium-orders";

export const fetchPremiumOrdersQuery = createAsyncThunk(
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
            return { data: res.data.data || [], meta: res.data.meta };
        } catch (err: any) {
            return rejectWithValue(
                err.response?.data?.message ||
                    "Không thể tải danh sách hóa đơn Premium"
            );
        }
    }
);

export const updatePremiumOrder = createAsyncThunk(
    `${prefix}/update`,
    async (
        { id, data }: { id: number; data: Record<string, any> },
        { rejectWithValue }
    ) => {
        try {
            const res = await api.put(`${prefix}/${id}`, data);
            return res.data.data || res.data;
        } catch (err: any) {
            return rejectWithValue(
                err.response?.data?.message || "Không thể cập nhật hóa đơn"
            );
        }
    }
);

export const deletePremiumOrder = createAsyncThunk(
    `${prefix}/delete`,
    async (id: number, { rejectWithValue }) => {
        try {
            await api.delete(`${prefix}/${id}`);
            return id;
        } catch (err: any) {
            return rejectWithValue(
                err.response?.data?.message || "Không thể xoá hóa đơn"
            );
        }
    }
);
