import { createSlice } from "@reduxjs/toolkit";
import { askAIQuery, fetchAIHistoryQuery } from "./aiChat.api";

interface ChatItem {
    sender: "user" | "ai";
    text: string;
}

interface ChatState {
    messages: ChatItem[];
    loading: boolean;
    error: string | null;
}

const initialState: ChatState = {
    messages: [],
    loading: false,
    error: null,
};

const aiChatSlice = createSlice({
    name: "aiChat",
    initialState,
    reducers: {
        clearMessages: (state) => {
            state.messages = [];
            state.loading = false;
            state.error = null;
        },
        pushUserMessage: (state, action) => {
            state.messages.push({
                sender: "user",
                text: action.payload,
            });
        },
        pushAIMessage: (state, action) => {
            state.messages.push({
                sender: "ai",
                text: action.payload,
            });
        },
    },
    extraReducers: (builder) => {
        builder
            .addCase(askAIQuery.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(askAIQuery.fulfilled, (state, action) => {
                state.loading = false;
                const html = action.payload?.data?.answer || "<p>Lỗi AI</p>";
                state.messages.push({
                    sender: "ai",
                    text: html,
                });
            })
            .addCase(askAIQuery.rejected, (state, action) => {
                state.loading = false;
                state.messages.push({
                    sender: "ai",
                    text: "<p>Lỗi kết nối server</p>",
                });
                state.error = action.payload as string;
            });

        builder
            .addCase(fetchAIHistoryQuery.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(fetchAIHistoryQuery.fulfilled, (state, action) => {
                state.loading = false;

                const history = action.payload || [];
                state.messages = [];
                history.forEach((item: any) => {
                    state.messages.push({
                        sender: "user",
                        text: item.question,
                    });
                    state.messages.push({
                        sender: "ai",
                        text: item.answer,
                    });
                });
            })
            .addCase(fetchAIHistoryQuery.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload as string;
            });
    },
});

export const { clearMessages, pushUserMessage, pushAIMessage } =
    aiChatSlice.actions;

export default aiChatSlice.reducer;
