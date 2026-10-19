import {
  BadRequestException,
  ForbiddenException,
  Inject,
  Injectable,
  NotFoundException,
} from '@nestjs/common';
import { Brackets, In, IsNull, LessThan, Repository } from 'typeorm';
import {
  BaseResDataI,
  CommunityConversationRepository,
  CommunityMessageRepository,
  HttpStatusCode,
  ResponseCode,
  UsersRepository,
} from 'src/shared';
import { UsersEntities } from '../Users/users.entities';
import {
  CommunityConversationEntity,
  CommunityMessageEntity,
} from './community.entities';
import { GetMessagesQueryDto } from './community.dto';
import {
  CommunityMember,
  MEMBER_COLUMNS,
  toCommunityMember,
} from './community-member';
import { CommunityRealtimeService } from './community-realtime.service';
import { ServerEvent } from './community.events';

const PREVIEW_LENGTH = 120;
const MEMBER_SEARCH_LIMIT = 20;
const DEFAULT_PAGE_SIZE = 30;

const ok = <T>(message: string, data: T): BaseResDataI<T> => ({
  status: HttpStatusCode.OK,
  code: ResponseCode.SUCCESS,
  message,
  data,
});

export interface MessageView {
  id: number;
  conversationId: number;
  senderId: number;
  recipientId: number;
  content: string;
  createdAt: Date;
  readAt: Date | null;
}

export interface ConversationView {
  id: number;
  partner: CommunityMember & { online: boolean };
  lastMessagePreview: string | null;
  lastSenderId: number | null;
  lastMessageAt: Date | null;
  unreadCount: number;
}

function toMessageView(message: CommunityMessageEntity): MessageView {
  return {
    id: message.id,
    conversationId: message.conversationId,
    senderId: message.senderId,
    recipientId: message.recipientId,
    content: message.content,
    createdAt: message.createdAt,
    readAt: message.readAt ?? null,
  };
}

const partnerIdOf = (
  conversation: CommunityConversationEntity,
  userId: number,
) =>
  conversation.userLowId === userId
    ? conversation.userHighId
    : conversation.userLowId;

@Injectable()
export class CommunityMessagesService {
  constructor(
    @Inject(CommunityConversationRepository)
    private readonly conversationRepo: Repository<CommunityConversationEntity>,
    @Inject(CommunityMessageRepository)
    private readonly messageRepo: Repository<CommunityMessageEntity>,
    @Inject(UsersRepository)
    private readonly usersRepo: Repository<UsersEntities>,
    private readonly realtime: CommunityRealtimeService,
  ) {}

  async searchMembers(viewerId: number, keyword?: string) {
    const qb = this.usersRepo
      .createQueryBuilder('user')
      .select(MEMBER_COLUMNS.map((column) => `user.${column}`))
      .where('user.active = :active', { active: true })
      .andWhere('user.id != :viewerId', { viewerId })
      .orderBy('user.fullName', 'ASC')
      .take(MEMBER_SEARCH_LIMIT);

    const term = keyword?.trim().toLowerCase();
    if (term) {
      qb.andWhere(
        new Brackets((where) =>
          where
            .where('LOWER(user.fullName) LIKE :term', { term: `%${term}%` })
            .orWhere('LOWER(user.username) LIKE :term', { term: `%${term}%` }),
        ),
      );
    }

    const users = await qb.getMany();
    return ok(
      'Danh sách thành viên',
      users.map((user) => this.withPresence(toCommunityMember(user))),
    );
  }

  async getMember(memberId: number) {
    const [member] = await this.loadMembers([memberId]);
    if (!member) throw new NotFoundException('Thành viên không tồn tại');
    return ok('Thông tin thành viên', this.withPresence(member));
  }

  async listConversations(userId: number) {
    const conversations = await this.conversationRepo
      .createQueryBuilder('conversation')
      .where('conversation.active = :active', { active: true })
      .andWhere(
        '(conversation.userLowId = :userId OR conversation.userHighId = :userId)',
        { userId },
      )
      .orderBy('conversation.lastMessageAt', 'DESC', 'NULLS LAST')
      .addOrderBy('conversation.id', 'DESC')
      .getMany();

    const [members, unread] = await Promise.all([
      this.loadMembers(conversations.map((c) => partnerIdOf(c, userId))),
      this.unreadCountsByConversation(userId),
    ]);
    const membersById = new Map(members.map((m) => [m.id, m]));

    const views = conversations.flatMap((conversation) => {
      const partner = membersById.get(partnerIdOf(conversation, userId));
      return partner
        ? [this.toConversationView(conversation, partner, unread)]
        : [];
    });

    return ok('Danh sách hội thoại', views);
  }

  async startConversation(userId: number, recipientId: number) {
    if (recipientId === userId) {
      throw new BadRequestException('Không thể tự nhắn tin cho chính mình');
    }
    const [partner] = await this.loadMembers([recipientId]);
    if (!partner) throw new NotFoundException('Thành viên không tồn tại');

    const conversation = await this.findOrCreateConversation(
      userId,
      recipientId,
    );
    const unread = await this.unreadCountsByConversation(userId, [
      conversation.id,
    ]);
    return ok(
      'Mở hội thoại thành công',
      this.toConversationView(conversation, partner, unread),
    );
  }

  async getMessages(
    userId: number,
    conversationId: number,
    query: GetMessagesQueryDto,
  ) {
    await this.findParticipantConversation(userId, conversationId);
    const limit = query.limit ?? DEFAULT_PAGE_SIZE;

    const rows = await this.messageRepo.find({
      where: {
        conversationId,
        active: true,
        ...(query.beforeId ? { id: LessThan(query.beforeId) } : {}),
      },
      order: { id: 'DESC' },
      take: limit + 1,
    });

    const hasMore = rows.length > limit;
    const messages = rows.slice(0, limit).reverse().map(toMessageView);
    return ok('Danh sách tin nhắn', { messages, hasMore });
  }

  async sendMessage(senderId: number, conversationId: number, content: string) {
    const text = content?.trim();
    if (!text) throw new BadRequestException('Tin nhắn không được để trống');
    if (text.length > 2000) {
      throw new BadRequestException('Tin nhắn tối đa 2000 ký tự');
    }

    const conversation = await this.findParticipantConversation(
      senderId,
      conversationId,
    );
    const recipientId = partnerIdOf(conversation, senderId);

    const message = await this.messageRepo.save(
      this.messageRepo.create({
        conversationId,
        senderId,
        recipientId,
        content: text,
        createdBy: senderId,
      }),
    );

    conversation.lastMessagePreview = text.slice(0, PREVIEW_LENGTH);
    conversation.lastSenderId = senderId;
    conversation.lastMessageAt = message.createdAt;
    await this.conversationRepo.save(conversation);

    await this.notifyNewMessage(conversation, message);
    return ok('Đã gửi tin nhắn', toMessageView(message));
  }

  async markRead(readerId: number, conversationId: number) {
    const conversation = await this.findParticipantConversation(
      readerId,
      conversationId,
    );
    const readAt = new Date();
    const result = await this.messageRepo.update(
      { conversationId, recipientId: readerId, readAt: IsNull() },
      { readAt },
    );

    if (result.affected) {
      this.realtime.emitToUsers(
        [conversation.userLowId, conversation.userHighId],
        ServerEvent.CONVERSATION_READ,
        { conversationId, readerId, readAt },
      );
    }
    return ok('Đã đánh dấu đã đọc', { conversationId, readAt });
  }

  /** Partner of `userId` in the conversation; throws if not a participant. */
  async partnerOf(userId: number, conversationId: number) {
    const conversation = await this.findParticipantConversation(
      userId,
      conversationId,
    );
    return partnerIdOf(conversation, userId);
  }

  private async notifyNewMessage(
    conversation: CommunityConversationEntity,
    message: CommunityMessageEntity,
  ) {
    const members = await this.loadMembers([
      message.senderId,
      message.recipientId,
    ]);
    const membersById = new Map(members.map((m) => [m.id, m]));
    const unread = await this.unreadCountsByConversation(message.recipientId, [
      conversation.id,
    ]);
    const payload = toMessageView(message);

    // Each side gets the conversation as seen from their own perspective.
    for (const [viewerId, partnerId, unreadCounts] of [
      [message.senderId, message.recipientId, new Map<number, number>()],
      [message.recipientId, message.senderId, unread],
    ] as const) {
      const partner = membersById.get(partnerId);
      if (!partner) continue;
      this.realtime.emitToUsers([viewerId], ServerEvent.MESSAGE_NEW, {
        message: payload,
        conversation: this.toConversationView(
          conversation,
          partner,
          unreadCounts,
        ),
      });
    }
  }

  private async findOrCreateConversation(userA: number, userB: number) {
    const [userLowId, userHighId] =
      userA < userB ? [userA, userB] : [userB, userA];
    const existing = await this.conversationRepo.findOne({
      where: { userLowId, userHighId },
    });
    if (existing) return existing;

    try {
      return await this.conversationRepo.save(
        this.conversationRepo.create({
          userLowId,
          userHighId,
          createdBy: userA,
        }),
      );
    } catch (err) {
      // Both members opened the conversation at the same moment: the unique
      // index rejected the second insert, so return the row that won.
      const winner = await this.conversationRepo.findOne({
        where: { userLowId, userHighId },
      });
      if (winner) return winner;
      throw err;
    }
  }

  private async findParticipantConversation(
    userId: number,
    conversationId: number,
  ) {
    const conversation = await this.conversationRepo.findOne({
      where: { id: conversationId, active: true },
    });
    if (!conversation) throw new NotFoundException('Hội thoại không tồn tại');
    if (
      conversation.userLowId !== userId &&
      conversation.userHighId !== userId
    ) {
      throw new ForbiddenException('Bạn không thuộc hội thoại này');
    }
    return conversation;
  }

  private async loadMembers(ids: number[]): Promise<CommunityMember[]> {
    const uniqueIds = [...new Set(ids)];
    if (uniqueIds.length === 0) return [];
    const users = await this.usersRepo.find({
      where: { id: In(uniqueIds), active: true },
      select: MEMBER_COLUMNS,
    });
    return users.map(toCommunityMember);
  }

  private async unreadCountsByConversation(
    userId: number,
    conversationIds?: number[],
  ): Promise<Map<number, number>> {
    const qb = this.messageRepo
      .createQueryBuilder('message')
      .select('message.conversationId', 'conversationId')
      .addSelect('COUNT(*)', 'count')
      .where('message.recipientId = :userId', { userId })
      .andWhere('message.readAt IS NULL')
      .andWhere('message.active = :active', { active: true })
      .groupBy('message.conversationId');
    if (conversationIds) {
      qb.andWhere('message.conversationId IN (:...conversationIds)', {
        conversationIds,
      });
    }

    const rows = await qb.getRawMany<{
      conversationId: number;
      count: string;
    }>();
    return new Map(
      rows.map((row) => [Number(row.conversationId), Number(row.count)]),
    );
  }

  private toConversationView(
    conversation: CommunityConversationEntity,
    partner: CommunityMember,
    unread: Map<number, number>,
  ): ConversationView {
    return {
      id: conversation.id,
      partner: this.withPresence(partner),
      lastMessagePreview: conversation.lastMessagePreview ?? null,
      lastSenderId: conversation.lastSenderId ?? null,
      lastMessageAt: conversation.lastMessageAt ?? null,
      unreadCount: unread.get(conversation.id) ?? 0,
    };
  }

  private withPresence(member: CommunityMember) {
    return { ...member, online: this.realtime.isOnline(member.id) };
  }
}
