import { createAsyncThunk } from "@reduxjs/toolkit";
import { api } from "@/utils/axiosInstance";

const prefix = "/stocks";

export const fetchStocksQuery = createAsyncThunk(
    `${prefix}/fetchQuery`,
    async (
        params: { page?: number; limit?: number; filters?: any },
        { rejectWithValue }
    ) => {
        try {
            const res = await api.get(`${prefix}`, { params });
            return res.data;
        } catch (err: any) {
            return rejectWithValue(
                err.response?.data?.message ||
                    "Không thể tải danh sách cổ phiếu"
            );
        }
    }
);
