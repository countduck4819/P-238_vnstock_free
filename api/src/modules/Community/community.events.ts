/** Socket.IO namespace and path shared with the web client. */
export const COMMUNITY_NAMESPACE = '/community';
export const COMMUNITY_SOCKET_PATH = '/api/socket.io';

/** Events the server pushes to clients. */
export const ServerEvent = {
  POST_CREATED: 'post:created',
  POST_DELETED: 'post:deleted',
  POST_LIKES: 'post:likes',
  COMMENT_CREATED: 'comment:created',
  COMMENT_DELETED: 'comment:deleted',
  MESSAGE_NEW: 'message:new',
  CONVERSATION_READ: 'conversation:read',
  TYPING: 'typing',
  PRESENCE_SNAPSHOT: 'presence:snapshot',
  PRESENCE_UPDATE: 'presence:update',
} as const;

/** Events clients send to the server. */
export const ClientEvent = {
  MESSAGE_SEND: 'message:send',
  CONVERSATION_READ: 'conversation:read',
  TYPING: 'typing',
} as const;

export const userRoom = (userId: number) => `user:${userId}`;
