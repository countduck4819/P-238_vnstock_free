import { createSlice, PayloadAction } from "@reduxjs/toolkit";
import {
    fetchConversations,
    fetchMessages,
    markConversationReadRest,
    openConversation,
    sendMessageRest,
} from "./community-chat.api";

export interface ChatMember {
    id: number;
    name: string;
    avatar: string | null;
    role: string;
    badge: string;
    online?: boolean;
}

export interface ChatMessage {
    id: number;
    conversationId: number;
    senderId: number;
    recipientId: number;
    content: string;
    createdAt: string;
    readAt: string | null;
}

export interface Conversation {
    id: number;
    partner: ChatMember;
    lastMessagePreview: string | null;
    lastSenderId: number | null;
    lastMessageAt: string | null;
    unreadCount: number;
}

interface MessageThread {
    items: ChatMessage[];
    hasMore: boolean;
    loading: boolean;
    loaded: boolean;
}

interface CommunityChatState {
    conversations: Conversation[];
    conversationsLoaded: boolean;
    threads: Record<number, MessageThread>;
    onlineUserIds: number[];
    /** conversationId -> the partner is typing */
    typing: Record<number, boolean>;
}

const initialState: CommunityChatState = {
    conversations: [],
    conversationsLoaded: false,
    threads: {},
    onlineUserIds: [],
    typing: {},
};

const emptyThread = (): MessageThread => ({
    items: [],
    hasMore: false,
    loading: false,
    loaded: false,
});

/** Inserts or refreshes a conversation and moves it to the top of the list. */
function upsertConversation(state: CommunityChatState, conversation: Conversation) {
    state.conversations = [
        conversation,
        ...state.conversations.filter((c) => c.id !== conversation.id),
    ];
}

function appendMessage(state: CommunityChatState, message: ChatMessage) {
    const thread = state.threads[message.conversationId];
    if (!thread?.loaded || thread.items.some((m) => m.id === message.id)) return;
    thread.items.push(message);
}

export const communityChatSlice = createSlice({
    name: "communityChat",
    initialState,
    reducers: {
        messageReceived: (
            state,
            action: PayloadAction<{ message: ChatMessage; conversation: Conversation }>
        ) => {
            const { message, conversation } = action.payload;
            upsertConversation(state, conversation);
            appendMessage(state, message);
            state.typing[message.conversationId] = false;
        },
        messageSent: (state, action: PayloadAction<ChatMessage>) => {
            const message = action.payload;
            appendMessage(state, message);
            const conversation = state.conversations.find((c) => c.id === message.conversationId);
            if (conversation) {
                upsertConversation(state, {
                    ...conversation,
                    lastMessagePreview: message.content.slice(0, 120),
                    lastSenderId: message.senderId,
                    lastMessageAt: message.createdAt,
                });
            }
        },
        conversationRead: (
            state,
            action: PayloadAction<{
                conversationId: number;
                readerId: number;
                readAt: string;
                viewerId: number;
            }>
        ) => {
            const { conversationId, readerId, readAt, viewerId } = action.payload;
            if (readerId === viewerId) {
                const conversation = state.conversations.find((c) => c.id === conversationId);
                if (conversation) conversation.unreadCount = 0;
            }
            for (const message of state.threads[conversationId]?.items ?? []) {
                if (message.recipientId === readerId && !message.readAt) message.readAt = readAt;
            }
        },
        typingChanged: (
            state,
            action: PayloadAction<{ conversationId: number; typing: boolean }>
        ) => {
            state.typing[action.payload.conversationId] = action.payload.typing;
        },
        presenceSnapshot: (state, action: PayloadAction<number[]>) => {
            state.onlineUserIds = action.payload;
        },
        presenceChanged: (state, action: PayloadAction<{ userId: number; online: boolean }>) => {
            const { userId, online } = action.payload;
            const others = state.onlineUserIds.filter((id) => id !== userId);
            state.onlineUserIds = online ? [...others, userId] : others;
        },
        chatReset: () => initialState,
    },
    extraReducers: (builder) => {
        builder.addCase(fetchConversations.fulfilled, (state, action) => {
            state.conversations = action.payload;
            state.conversationsLoaded = true;
        });

        builder.addCase(openConversation.fulfilled, (state, action) => {
            const conversation = action.payload;
            if (!state.conversations.some((c) => c.id === conversation.id)) {
                state.conversations.unshift(conversation);
            }
        });

        builder
            .addCase(fetchMessages.pending, (state, action) => {
                const { conversationId } = action.meta.arg;
                state.threads[conversationId] ??= emptyThread();
                state.threads[conversationId].loading = true;
            })
            .addCase(fetchMessages.fulfilled, (state, action) => {
                const { conversationId, messages, hasMore } = action.payload;
                const thread = state.threads[conversationId];
                const known = new Set(thread.items.map((m) => m.id));
                const fresh = messages.filter((m) => !known.has(m.id));
                thread.items = [...thread.items, ...fresh].sort((a, b) => a.id - b.id);
                thread.hasMore = hasMore;
                thread.loading = false;
                thread.loaded = true;
            })
            .addCase(fetchMessages.rejected, (state, action) => {
                const thread = state.threads[action.meta.arg.conversationId];
                if (thread) thread.loading = false;
            });

        builder.addCase(sendMessageRest.fulfilled, (state, action) => {
            communityChatSlice.caseReducers.messageSent(state, {
                type: "communityChat/messageSent",
                payload: action.payload,
            });
        });

        builder.addCase(markConversationReadRest.fulfilled, (state, action) => {
            const conversation = state.conversations.find((c) => c.id === action.payload);
            if (conversation) conversation.unreadCount = 0;
        });
    },
});

export const {
    messageReceived,
    messageSent,
    conversationRead,
    typingChanged,
    presenceSnapshot,
    presenceChanged,
    chatReset,
} = communityChatSlice.actions;

export const selectUnreadTotal = (state: { communityChat: CommunityChatState }) =>
    state.communityChat.conversations.reduce((sum, c) => sum + c.unreadCount, 0);

export default communityChatSlice.reducer;
