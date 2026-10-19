import { io, Socket } from "socket.io-client";
import { getCookie } from "@/utils/axiosInstance";

// Must match api/src/modules/Community/community.events.ts
export const COMMUNITY_NAMESPACE = "/community";
export const COMMUNITY_SOCKET_PATH = "/api/socket.io";

export const ServerEvent = {
    POST_CREATED: "post:created",
    POST_DELETED: "post:deleted",
    POST_LIKES: "post:likes",
    COMMENT_CREATED: "comment:created",
    COMMENT_DELETED: "comment:deleted",
    MESSAGE_NEW: "message:new",
    CONVERSATION_READ: "conversation:read",
    TYPING: "typing",
    PRESENCE_SNAPSHOT: "presence:snapshot",
    PRESENCE_UPDATE: "presence:update",
} as const;

export const ClientEvent = {
    MESSAGE_SEND: "message:send",
    CONVERSATION_READ: "conversation:read",
    TYPING: "typing",
} as const;

export type SocketAck<T> = { ok: true; data: T } | { ok: false; error: string };

/**
 * Opens the community socket on the same origin as the page: nginx (and the
 * Next.js /api rewrite in development) forwards `/api/socket.io` to the API.
 * NEXT_PUBLIC_SOCKET_URL can point it at another host when needed.
 */
export function createCommunitySocket(): Socket {
    const baseUrl = process.env.NEXT_PUBLIC_SOCKET_URL || window.location.origin;
    return io(`${baseUrl.replace(/\/$/, "")}${COMMUNITY_NAMESPACE}`, {
        path: COMMUNITY_SOCKET_PATH,
        // Matches the server: survives Next.js' trailing-slash redirect.
        addTrailingSlash: false,
        // Evaluated on every (re)connect so a refreshed token is picked up.
        auth: (cb) => cb({ token: getCookie("accessToken") ?? undefined }),
        withCredentials: true,
    });
}
