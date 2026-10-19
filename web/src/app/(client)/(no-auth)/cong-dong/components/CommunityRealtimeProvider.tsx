"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import type { Socket } from "socket.io-client";
import { useAuth } from "@/auth/AuthProvider";
import { useAppDispatch } from "@/redux/hooks";
import {
    ClientEvent,
    ServerEvent,
    SocketAck,
    createCommunitySocket,
} from "@/utils/communitySocket";
import {
    commentReceived,
    commentRemoved,
    CommentItem,
    CommunityPost,
    postLikesChanged,
    postReceived,
    postRemoved,
} from "@/store/community/community.reducer";
import {
    chatReset,
    ChatMessage,
    Conversation,
    conversationRead,
    messageReceived,
    messageSent,
    presenceChanged,
    presenceSnapshot,
    typingChanged,
} from "@/store/community-chat/community-chat.reducer";
import {
    fetchConversations,
    markConversationReadRest,
    sendMessageRest,
} from "@/store/community-chat/community-chat.api";

interface CommunityRealtimeContextValue {
    connected: boolean;
    sendMessage: (conversationId: number, content: string) => Promise<ChatMessage>;
    markRead: (conversationId: number) => void;
    setTyping: (conversationId: number, typing: boolean) => void;
}

const CommunityRealtimeContext = createContext<CommunityRealtimeContextValue | null>(null);

/**
 * Owns the community socket for every page under /cong-dong: feed updates,
 * direct messages, read receipts, typing and online presence all flow
 * through here into Redux. Sending prefers the socket and falls back to REST.
 */
export function CommunityRealtimeProvider({ children }: { children: React.ReactNode }) {
    const dispatch = useAppDispatch();
    const { user } = useAuth();
    const viewerId = user?.id;
    const socketRef = useRef<Socket | null>(null);
    const [connected, setConnected] = useState(false);

    useEffect(() => {
        const socket = createCommunitySocket();
        socketRef.current = socket;

        socket.on("connect", () => setConnected(true));
        socket.on("disconnect", () => setConnected(false));

        socket.on(ServerEvent.POST_CREATED, (post: CommunityPost) => dispatch(postReceived(post)));
        socket.on(ServerEvent.POST_DELETED, (payload: { postId: string }) =>
            dispatch(postRemoved(payload))
        );
        socket.on(ServerEvent.POST_LIKES, (payload: { postId: string; likesCount: number }) =>
            dispatch(postLikesChanged(payload))
        );
        socket.on(ServerEvent.COMMENT_CREATED, (comment: CommentItem & { postId: string }) =>
            dispatch(commentReceived(comment))
        );
        socket.on(ServerEvent.COMMENT_DELETED, (payload: { postId: string; commentId: string }) =>
            dispatch(commentRemoved(payload))
        );

        socket.on(
            ServerEvent.MESSAGE_NEW,
            (payload: { message: ChatMessage; conversation: Conversation }) =>
                dispatch(messageReceived(payload))
        );
        socket.on(
            ServerEvent.CONVERSATION_READ,
            (payload: { conversationId: number; readerId: number; readAt: string }) => {
                if (viewerId) dispatch(conversationRead({ ...payload, viewerId }));
            }
        );
        socket.on(
            ServerEvent.TYPING,
            (payload: { conversationId: number; typing: boolean }) =>
                dispatch(typingChanged(payload))
        );
        socket.on(ServerEvent.PRESENCE_SNAPSHOT, (ids: number[]) => dispatch(presenceSnapshot(ids)));
        socket.on(ServerEvent.PRESENCE_UPDATE, (payload: { userId: number; online: boolean }) =>
            dispatch(presenceChanged(payload))
        );

        if (viewerId) dispatch(fetchConversations());

        return () => {
            socket.disconnect();
            socketRef.current = null;
            setConnected(false);
            dispatch(chatReset());
        };
        // Reconnect with the new identity whenever the signed-in account changes.
    }, [dispatch, viewerId]);

    const sendMessage = useCallback(
        async (conversationId: number, content: string) => {
            const socket = socketRef.current;
            if (socket?.connected) {
                const ack: SocketAck<ChatMessage> = await socket
                    .timeout(10000)
                    .emitWithAck(ClientEvent.MESSAGE_SEND, { conversationId, content });
                if (!ack.ok) throw new Error(ack.error);
                dispatch(messageSent(ack.data));
                return ack.data;
            }
            return dispatch(sendMessageRest({ conversationId, content })).unwrap();
        },
        [dispatch]
    );

    const markRead = useCallback(
        (conversationId: number) => {
            const socket = socketRef.current;
            if (socket?.connected) {
                socket.emit(ClientEvent.CONVERSATION_READ, { conversationId });
            } else {
                dispatch(markConversationReadRest(conversationId));
            }
        },
        [dispatch]
    );

    const setTyping = useCallback((conversationId: number, typing: boolean) => {
        socketRef.current?.emit(ClientEvent.TYPING, { conversationId, typing });
    }, []);

    return (
        <CommunityRealtimeContext.Provider value={{ connected, sendMessage, markRead, setTyping }}>
            {children}
        </CommunityRealtimeContext.Provider>
    );
}

export function useCommunityRealtime() {
    const ctx = useContext(CommunityRealtimeContext);
    if (!ctx) {
        throw new Error("useCommunityRealtime must be used within CommunityRealtimeProvider");
    }
    return ctx;
}
