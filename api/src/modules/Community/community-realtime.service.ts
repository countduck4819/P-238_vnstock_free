import { Injectable } from '@nestjs/common';
import type { Namespace } from 'socket.io';
import { ServerEvent, userRoom } from './community.events';

/**
 * Thin wrapper around the community Socket.IO namespace so services can push
 * events without depending on the gateway (which itself depends on them).
 * Also keeps the per-user connection count used for online presence.
 */
@Injectable()
export class CommunityRealtimeService {
  private server?: Namespace;
  private readonly connections = new Map<number, number>();

  attach(server: Namespace) {
    this.server = server;
  }

  broadcast(event: string, payload: unknown) {
    this.server?.emit(event, payload);
  }

  emitToUsers(userIds: number[], event: string, payload: unknown) {
    if (!this.server || userIds.length === 0) return;
    const rooms = [...new Set(userIds)].map(userRoom);
    this.server.to(rooms).emit(event, payload);
  }

  onlineUserIds(): number[] {
    return [...this.connections.keys()];
  }

  isOnline(userId: number): boolean {
    return this.connections.has(userId);
  }

  /** Counts a new socket; announces the user online on their first one. */
  markConnected(userId: number) {
    const count = this.connections.get(userId) ?? 0;
    this.connections.set(userId, count + 1);
    if (count === 0) {
      this.broadcast(ServerEvent.PRESENCE_UPDATE, { userId, online: true });
    }
  }

  /** Releases a socket; announces the user offline when none remain. */
  markDisconnected(userId: number) {
    const count = this.connections.get(userId) ?? 0;
    if (count > 1) {
      this.connections.set(userId, count - 1);
      return;
    }
    this.connections.delete(userId);
    this.broadcast(ServerEvent.PRESENCE_UPDATE, { userId, online: false });
  }
}
