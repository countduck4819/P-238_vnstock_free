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
    authorId?: number;
}

// The author is the signed-in account: the API reads it from the access token.
export interface CreatePostPayload {
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
    postId: string;
    content: string;
}

const errorMessage = (err: unknown, fallback: string) =>
    typeof err === "string" ? err : fallback;

export const fetchCommunityPosts = createAsyncThunk(
    `${prefix}/fetchPosts`,
    async (params: GetPostsParams = {}, { rejectWithValue }) => {
        try {
            const res = await api.get(`${prefix}/posts`, { params });
            return res.data?.data;
        } catch (err) {
            return rejectWithValue(errorMessage(err, "Không thể tải danh sách bài viết"));
        }
    }
);

export const createCommunityPost = createAsyncThunk(
    `${prefix}/createPost`,
    async (body: CreatePostPayload, { rejectWithValue }) => {
        try {
            const res = await api.post(`${prefix}/posts`, body);
            return res.data?.data;
        } catch (err) {
            return rejectWithValue(errorMessage(err, "Không thể đăng bài viết"));
        }
    }
);

export const toggleLikeCommunityPost = createAsyncThunk(
    `${prefix}/toggleLike`,
    async (postId: string, { rejectWithValue }) => {
        try {
            const res = await api.post(`${prefix}/posts/${postId}/like`, {});
            return { postId, ...res.data?.data };
        } catch (err) {
            return rejectWithValue(errorMessage(err, "Không thể thả tim bài viết"));
        }
    }
);

export const toggleSaveCommunityPost = createAsyncThunk(
    `${prefix}/toggleSave`,
    async (postId: string, { rejectWithValue }) => {
        try {
            const res = await api.post(`${prefix}/posts/${postId}/save`, {});
            return { postId, ...res.data?.data };
        } catch (err) {
            return rejectWithValue(errorMessage(err, "Không thể lưu bài viết"));
        }
    }
);

export const addCommunityComment = createAsyncThunk(
    `${prefix}/addComment`,
    async ({ postId, content }: CreateCommentPayload, { rejectWithValue }) => {
        try {
            const res = await api.post(`${prefix}/posts/${postId}/comments`, { content });
            return { postId, comment: res.data?.data };
        } catch (err) {
            return rejectWithValue(errorMessage(err, "Không thể gửi bình luận"));
        }
    }
);

export const deleteCommunityComment = createAsyncThunk(
    `${prefix}/deleteComment`,
    async ({ postId, commentId }: { postId: string; commentId: string }, { rejectWithValue }) => {
        try {
            await api.delete(`${prefix}/comments/${commentId}`);
            return { postId, commentId };
        } catch (err) {
            return rejectWithValue(errorMessage(err, "Không thể xóa bình luận"));
        }
    }
);

export const deleteCommunityPost = createAsyncThunk(
    `${prefix}/deletePost`,
    async (postId: string, { rejectWithValue }) => {
        try {
            await api.delete(`${prefix}/posts/${postId}`);
            return postId;
        } catch (err) {
            return rejectWithValue(errorMessage(err, "Không thể xóa bài viết"));
        }
    }
);
