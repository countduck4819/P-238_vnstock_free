import { createAsyncThunk } from "@reduxjs/toolkit";
import { api } from "@/utils/axiosInstance";

const prefix = "/ai-stock";

export const askAIQuery = createAsyncThunk(
    `${prefix}/ask`,
    async (body: { userId?: number; question: string }, { rejectWithValue }) => {
        try {
            const res = await api.post(`${prefix}/ask`, body);
            return res.data;
        } catch (err: any) {
            return rejectWithValue(
                err.response?.data?.message || "Không thể gửi câu hỏi cho AI"
            );
        }
    }
);

export const fetchAIHistoryQuery = createAsyncThunk(
    `${prefix}/history`,
    async (userId: number, { rejectWithValue }) => {
        try {
            const res = await api.get(`${prefix}/history/${userId}`);
            return res.data?.data;
        } catch (err: any) {
            return rejectWithValue(
                err.response?.data?.message || "Không thể lấy lịch sử AI"
            );
        }
    }
);
