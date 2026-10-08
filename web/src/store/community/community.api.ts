import { createAsyncThunk } from "@reduxjs/toolkit";
import { api } from "@/utils/axiosInstance";

const prefix = "/community";

export interface GetPostsParams {
    page?: number;
    limit?: number;
    category?: string;
    sector?: string;
    symbol?: string;
    keyword?: string;
    userId?: number;
}

export interface CreatePostPayload {
    userId?: number;
    authorName?: string;
    authorAvatar?: string;
    authorRole?: string;
    authorBadge?: string;
    title?: string;
    content: string;
    symbol?: string;
    stance?: string;
    targetPrice?: number;
    stopLossPrice?: number;
    category?: string;
    sector?: string;
    imageUrl?: string;
}

export interface CreateCommentPayload {
    postId: string | number;
    content: string;
    userId?: number;
    authorName?: string;
    authorAvatar?: string;
}

export const fetchCommunityPosts = createAsyncThunk(
    `${prefix}/fetchPosts`,
    async (params: GetPostsParams = {}, { rejectWithValue }) => {
        try {
            const res = await api.get(`${prefix}/posts`, { params });
            return res.data?.data;
        } catch (err: any) {
            return rejectWithValue(
                err.response?.data?.message || "Không thể tải danh sách bài viết"
            );
        }
    }
);

export const createCommunityPost = createAsyncThunk(
    `${prefix}/createPost`,
    async (body: CreatePostPayload, { rejectWithValue }) => {
        try {
            const res = await api.post(`${prefix}/posts`, body);
            return res.data?.data;
        } catch (err: any) {
            return rejectWithValue(
                err.response?.data?.message || "Không thể đăng bài viết"
            );
        }
    }
);

export const toggleLikeCommunityPost = createAsyncThunk(
    `${prefix}/toggleLike`,
    async (
        { postId, userId }: { postId: string | number; userId?: number },
        { rejectWithValue }
    ) => {
        try {
            const res = await api.post(`${prefix}/posts/${postId}/like`, { userId });
            return { postId: String(postId), ...res.data?.data };
        } catch (err: any) {
            return rejectWithValue(
                err.response?.data?.message || "Không thể thả tim bài viết"
            );
        }
    }
);

export const toggleSaveCommunityPost = createAsyncThunk(
    `${prefix}/toggleSave`,
    async (
        { postId, userId }: { postId: string | number; userId?: number },
        { rejectWithValue }
    ) => {
        try {
            const res = await api.post(`${prefix}/posts/${postId}/save`, { userId });
            return { postId: String(postId), ...res.data?.data };
        } catch (err: any) {
            return rejectWithValue(
                err.response?.data?.message || "Không thể lưu bài viết"
            );
        }
    }
);

export const addCommunityComment = createAsyncThunk(
    `${prefix}/addComment`,
    async (payload: CreateCommentPayload, { rejectWithValue }) => {
        const { postId, ...rest } = payload;
        try {
            const res = await api.post(`${prefix}/posts/${postId}/comments`, rest);
            return { postId: String(postId), comment: res.data?.data };
        } catch (err: any) {
            return rejectWithValue(
                err.response?.data?.message || "Không thể gửi bình luận"
            );
        }
    }
);

export const deleteCommunityPost = createAsyncThunk(
    `${prefix}/deletePost`,
    async (
        payload: { postId: string | number; userId?: number; role?: string } | string | number,
        { rejectWithValue }
    ) => {
        const postId = typeof payload === "object" ? payload.postId : payload;
        const params = typeof payload === "object" ? { userId: payload.userId, role: payload.role } : {};
        try {
            await api.delete(`${prefix}/posts/${postId}`, { params });
            return String(postId);
        } catch (err: any) {
            return rejectWithValue(
                err.response?.data?.message || "Không thể xóa bài viết"
            );
        }
    }
);
