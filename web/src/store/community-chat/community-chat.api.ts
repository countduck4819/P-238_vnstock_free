import { createAsyncThunk } from "@reduxjs/toolkit";
import { api } from "@/utils/axiosInstance";
import type { ChatMember, ChatMessage, Conversation } from "./community-chat.reducer";

const prefix = "/community";

const errorMessage = (err: unknown, fallback: string) =>
    typeof err === "string" ? err : fallback;

export const fetchConversations = createAsyncThunk(
    `${prefix}/fetchConversations`,
    async (_: void, { rejectWithValue }) => {
        try {
            const res = await api.get(`${prefix}/conversations`);
            return (res.data?.data ?? []) as Conversation[];
        } catch (err) {
            return rejectWithValue(errorMessage(err, "Không thể tải danh sách hội thoại"));
        }
    }
);

export const openConversation = createAsyncThunk(
    `${prefix}/openConversation`,
    async (recipientId: number, { rejectWithValue }) => {
        try {
            const res = await api.post(`${prefix}/conversations`, { recipientId });
            return res.data?.data as Conversation;
        } catch (err) {
            return rejectWithValue(errorMessage(err, "Không thể mở hội thoại"));
        }
    }
);

export const fetchMessages = createAsyncThunk(
    `${prefix}/fetchMessages`,
    async (
        { conversationId, beforeId }: { conversationId: number; beforeId?: number },
        { rejectWithValue }
    ) => {
        try {
            const res = await api.get(`${prefix}/conversations/${conversationId}/messages`, {
                params: { beforeId },
            });
            const data = res.data?.data as { messages: ChatMessage[]; hasMore: boolean };
            return { conversationId, beforeId, ...data };
        } catch (err) {
            return rejectWithValue(errorMessage(err, "Không thể tải tin nhắn"));
        }
    }
);

/** REST fallback used when the socket is not connected. */
export const sendMessageRest = createAsyncThunk(
    `${prefix}/sendMessage`,
    async (
        { conversationId, content }: { conversationId: number; content: string },
        { rejectWithValue }
    ) => {
        try {
            const res = await api.post(`${prefix}/conversations/${conversationId}/messages`, {
                content,
            });
            return res.data?.data as ChatMessage;
        } catch (err) {
            return rejectWithValue(errorMessage(err, "Không thể gửi tin nhắn"));
        }
    }
);

export const markConversationReadRest = createAsyncThunk(
    `${prefix}/markRead`,
    async (conversationId: number, { rejectWithValue }) => {
        try {
            await api.post(`${prefix}/conversations/${conversationId}/read`, {});
            return conversationId;
        } catch (err) {
            return rejectWithValue(errorMessage(err, "Không thể đánh dấu đã đọc"));
        }
    }
);

export async function searchMembers(keyword: string): Promise<ChatMember[]> {
    const res = await api.get(`${prefix}/members`, { params: { keyword } });
    return res.data?.data ?? [];
}
