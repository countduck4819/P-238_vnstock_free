import { HttpException, Inject, Logger } from '@nestjs/common';
import { JwtService } from '@nestjs/jwt';
import {
  ConnectedSocket,
  MessageBody,
  OnGatewayConnection,
  OnGatewayDisconnect,
  OnGatewayInit,
  SubscribeMessage,
  WebSocketGateway,
} from '@nestjs/websockets';
import type { Namespace, Socket } from 'socket.io';
import { ALLOWED_ORIGINS, CommunityMessagesServiceToken } from 'src/shared';
import { CommunityMessagesService } from './community-messages.service';
import { CommunityRealtimeService } from './community-realtime.service';
import {
  ClientEvent,
  COMMUNITY_NAMESPACE,
  COMMUNITY_SOCKET_PATH,
  ServerEvent,
  userRoom,
} from './community.events';

type Ack<T> = { ok: true; data: T } | { ok: false; error: string };

interface SocketData {
  userId: number;
}

type CommunitySocket = Socket<any, any, any, SocketData>;

/**
 * Realtime channel for the community: authenticated with the same JWT as the
 * REST API. Each socket joins a private `user:<id>` room so direct messages
 * reach every tab of the recipient; feed events are broadcast to everyone.
 */
@WebSocketGateway({
  namespace: COMMUNITY_NAMESPACE,
  path: COMMUNITY_SOCKET_PATH,
  // Next.js strips trailing slashes before its /api rewrite, so the polling
  // transport must work on `/api/socket.io?…` as well as behind nginx.
  addTrailingSlash: false,
  cors: { origin: ALLOWED_ORIGINS, credentials: true },
})
export class CommunityGateway
  implements OnGatewayInit, OnGatewayConnection, OnGatewayDisconnect
{
  private readonly logger = new Logger(CommunityGateway.name);

  constructor(
    private readonly jwtService: JwtService,
    private readonly realtime: CommunityRealtimeService,
    @Inject(CommunityMessagesServiceToken)
    private readonly messagesService: CommunityMessagesService,
  ) {}

  afterInit(server: Namespace) {
    this.realtime.attach(server);
  }

  async handleConnection(client: CommunitySocket) {
    const userId = await this.authenticate(client);
    if (!userId) {
      // Guests still receive public feed events; they just cannot chat.
      client.emit(ServerEvent.PRESENCE_SNAPSHOT, this.realtime.onlineUserIds());
      return;
    }

    client.data.userId = userId;
    await client.join(userRoom(userId));
    this.realtime.markConnected(userId);
    client.emit(ServerEvent.PRESENCE_SNAPSHOT, this.realtime.onlineUserIds());
  }

  handleDisconnect(client: CommunitySocket) {
    const { userId } = client.data;
    if (userId) this.realtime.markDisconnected(userId);
  }

  @SubscribeMessage(ClientEvent.MESSAGE_SEND)
  sendMessage(
    @ConnectedSocket() client: CommunitySocket,
    @MessageBody() body: { conversationId?: number; content?: string },
  ) {
    return this.run(client, async (userId) => {
      const result = await this.messagesService.sendMessage(
        userId,
        Number(body?.conversationId),
        String(body?.content ?? ''),
      );
      return result.data;
    });
  }

  @SubscribeMessage(ClientEvent.CONVERSATION_READ)
  markRead(
    @ConnectedSocket() client: CommunitySocket,
    @MessageBody() body: { conversationId?: number },
  ) {
    return this.run(client, async (userId) => {
      const result = await this.messagesService.markRead(
        userId,
        Number(body?.conversationId),
      );
      return result.data;
    });
  }

  @SubscribeMessage(ClientEvent.TYPING)
  typing(
    @ConnectedSocket() client: CommunitySocket,
    @MessageBody() body: { conversationId?: number; typing?: boolean },
  ) {
    return this.run(client, async (userId) => {
      const conversationId = Number(body?.conversationId);
      const partnerId = await this.messagesService.partnerOf(
        userId,
        conversationId,
      );
      this.realtime.emitToUsers([partnerId], ServerEvent.TYPING, {
        conversationId,
        userId,
        typing: body?.typing !== false,
      });
      return null;
    });
  }

  private async authenticate(client: CommunitySocket): Promise<number | null> {
    const fromAuth = client.handshake.auth?.token as string | undefined;
    const fromHeader = client.handshake.headers.authorization;
    const token = (fromAuth ?? fromHeader ?? '').replace(/^Bearer\s+/i, '');
    if (!token) return null;

    try {
      const payload = await this.jwtService.verifyAsync<{ sub: number }>(token);
      return Number(payload.sub) || null;
    } catch {
      client.emit('auth:error', { message: 'Phiên đăng nhập không hợp lệ' });
      return null;
    }
  }

  /** Runs an authenticated handler and converts the outcome into an ack. */
  private async run<T>(
    client: CommunitySocket,
    handler: (userId: number) => Promise<T>,
  ): Promise<Ack<T>> {
    const { userId } = client.data;
    if (!userId) return { ok: false, error: 'Vui lòng đăng nhập' };

    try {
      return { ok: true, data: await handler(userId) };
    } catch (err) {
      if (err instanceof HttpException) {
        return { ok: false, error: err.message };
      }
      this.logger.error('Community socket handler failed', err as Error);
      return { ok: false, error: 'Đã xảy ra lỗi, vui lòng thử lại' };
    }
  }
}
