import {
  ForbiddenException,
  Inject,
  Injectable,
  Logger,
  NotFoundException,
  OnModuleInit,
} from '@nestjs/common';
import { In, Repository } from 'typeorm';
import {
  CommunityPostEntity,
  CommunityCommentEntity,
  CommunityLikeEntity,
  CommunitySaveEntity,
} from './community.entities';
import {
  BaseResDataI,
  CommunityCommentRepository,
  CommunityLikeRepository,
  CommunityPostRepository,
  CommunitySaveRepository,
  HttpStatusCode,
  ResponseCode,
  UserRole,
  UsersRepository,
} from 'src/shared';
import { AuthUser } from 'src/shared/decorator/current-user.decorator';
import { UsersEntities } from '../Users/users.entities';
import {
  CreateCommunityCommentDto,
  CreateCommunityPostDto,
  GetCommunityPostsQueryDto,
} from './community.dto';
import { CommunityRealtimeService } from './community-realtime.service';
import { ServerEvent } from './community.events';
import { MEMBER_COLUMNS, toCommunityMember } from './community-member';

const SEED_POSTS: Partial<CommunityPostEntity>[] = [
  {
    authorName: 'Vũ Tuấn Anh - CFA',
    authorAvatar:
      'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=150&auto=format&fit=crop&q=80',
    authorRole: 'Trưởng phòng Phân tích Kỹ thuật',
    authorBadge: 'Chuyên gia',
    title:
      'FPT bứt phá đỉnh lịch sử: Triển vọng dòng tiền AI & Chuyển đổi số toàn cầu',
    content:
      'FPT vừa hoàn tất mẫu hình Cup & Handle trên đồ thị tuần với thanh khoản gấp 2.5 lần trung bình 20 phiên. Dòng tiền ngoại quay lại gom ròng mạnh mẽ sau thông tin hợp tác bán dẫn. Vùng hỗ trợ cứng quanh 130-132k, kỳ vọng sóng 5 đẩy giá tiệm cận mốc 160k trong Q4/2026.',
    symbol: 'FPT',
    stance: 'BUY',
    targetPrice: 160.0,
    stopLossPrice: 128.0,
    category: 'technical',
    sector: 'Công nghệ',
    imageUrl:
      'https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=800&auto=format&fit=crop&q=80',
    likesCount: 128,
    commentsCount: 2,
    viewsCount: 1420,
  },
  {
    authorName: 'FinSight AI Analyst',
    authorAvatar:
      'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=150&auto=format&fit=crop&q=80',
    authorRole: 'Hệ thống Phân tích AI FinSight',
    authorBadge: 'AI Analyst',
    title:
      'Cảnh báo Tín hiệu Sớm: Nhóm Thép (HPG, HSG) bước vào pha Tích lũy Siêu chu kỳ',
    content:
      'Mô hình Wave V6 Deep Learning phát hiện chu kỳ gom hàng của dòng tiền lớn tại nhóm Thép sau khi giá thép HRC thế giới phục hồi 8.5%. Biên lợi nhuận gộp của HPG dự phóng đạt đỉnh mới trong 2 quý tới. Khuyến nghị giải ngân tỷ trọng 30% danh mục.',
    symbol: 'HPG',
    stance: 'BUY',
    targetPrice: 35.5,
    stopLossPrice: 26.8,
    category: 'signal',
    sector: 'Thép & Vật liệu',
    likesCount: 95,
    commentsCount: 1,
    viewsCount: 980,
  },
  {
    authorName: 'Hoàng Yến Nhi',
    authorAvatar:
      'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=150&auto=format&fit=crop&q=80',
    authorRole: 'Nhà đầu tư Cá nhân VIP',
    authorBadge: 'VIP Trader',
    title:
      'Góc nhìn TCB: Động lực tăng trưởng từ CASA và tín dụng Bất động sản',
    content:
      'TCB duy trì tỷ lệ CASA top 1 hệ thống ngân hàng (~40%). Định giá P/B hiện tại 1.1x vẫn đang chiết khấu hấp dẫn so với trung bình 5 năm (1.4x). Dòng tiền cá nhân và tổ chức đang bắt đầu mở vị thế đón đầu kỳ công bố BCTC quý.',
    symbol: 'TCB',
    stance: 'BUY',
    targetPrice: 42.0,
    stopLossPrice: 32.5,
    category: 'fundamental',
    sector: 'Ngân hàng',
    likesCount: 64,
    commentsCount: 1,
    viewsCount: 760,
  },
];

const SEED_COMMENTS: Record<string, Partial<CommunityCommentEntity>[]> = {
  FPT: [
    {
      authorName: 'Trần Minh Quang',
      content:
        'Đồng quan điểm! Nhịp này FPT tích lũy rất chặt chẽ, target 160k hoàn toàn khả thi.',
      likesCount: 12,
    },
    {
      authorName: 'Lê Thảo My',
      content:
        'Khối ngoại vừa gom ròng hơn 150 tỷ phiên hôm qua, xu hướng cực kỳ rõ ràng.',
      likesCount: 5,
    },
  ],
  HPG: [
    {
      authorName: 'Nguyễn Văn Hùng',
      content:
        'Dung Quất 2 sắp đi vào vận hành sẽ là động lực tăng trưởng lớn cho HPG!',
      likesCount: 8,
    },
  ],
};

const ok = <T>(message: string, data: T): BaseResDataI<T> => ({
  status: HttpStatusCode.OK,
  code: ResponseCode.SUCCESS,
  message,
  data,
});

function toCommentView(comment: CommunityCommentEntity) {
  return {
    id: String(comment.id),
    postId: String(comment.postId),
    userId: comment.userId,
    authorName: comment.authorName,
    authorAvatar: comment.authorAvatar,
    content: comment.content,
    likes: comment.likesCount,
    createdAt: comment.createdAt,
  };
}

type CommentView = ReturnType<typeof toCommentView>;

function toPostView(
  post: CommunityPostEntity,
  comments: CommentView[],
  viewer: { isLiked: boolean; isSaved: boolean },
) {
  return {
    id: String(post.id),
    userId: post.userId,
    authorName: post.authorName,
    authorAvatar: post.authorAvatar,
    authorRole: post.authorRole,
    authorBadge: post.authorBadge,
    title: post.title,
    content: post.content,
    symbol: post.symbol,
    stance: post.stance,
    targetPrice: post.targetPrice,
    stopLossPrice: post.stopLossPrice,
    category: post.category,
    sector: post.sector,
    imageUrl: post.imageUrl,
    likes: post.likesCount,
    commentsCount: post.commentsCount,
    viewsCount: post.viewsCount,
    createdAt: post.createdAt,
    comments,
    ...viewer,
  };
}

@Injectable()
export class CommunityService implements OnModuleInit {
  private readonly logger = new Logger(CommunityService.name);

  constructor(
    @Inject(CommunityPostRepository)
    private readonly postRepo: Repository<CommunityPostEntity>,
    @Inject(CommunityCommentRepository)
    private readonly commentRepo: Repository<CommunityCommentEntity>,
    @Inject(CommunityLikeRepository)
    private readonly likeRepo: Repository<CommunityLikeEntity>,
    @Inject(CommunitySaveRepository)
    private readonly saveRepo: Repository<CommunitySaveEntity>,
    @Inject(UsersRepository)
    private readonly usersRepo: Repository<UsersEntities>,
    private readonly realtime: CommunityRealtimeService,
  ) {}

  async onModuleInit() {
    await this.seedInitialPostsIfEmpty();
  }

  private async seedInitialPostsIfEmpty() {
    try {
      if ((await this.postRepo.count()) > 0) return;

      this.logger.log('Seeding initial community posts...');
      for (const postData of SEED_POSTS) {
        const saved = await this.postRepo.save(this.postRepo.create(postData));
        const comments = SEED_COMMENTS[saved.symbol ?? ''] ?? [];
        if (comments.length > 0) {
          await this.commentRepo.save(
            comments.map((comment) => ({ ...comment, postId: saved.id })),
          );
        }
      }
      this.logger.log('Seeded initial community posts successfully.');
    } catch (err) {
      this.logger.error('Failed to seed community posts', err);
    }
  }

  async getPosts(query: GetCommunityPostsQueryDto, viewerId?: number) {
    const page = query.page ?? 1;
    const limit = query.limit ?? 20;
    const empty = { posts: [], total: 0, page, limit };

    const qb = this.postRepo
      .createQueryBuilder('post')
      .where('post.active = :active', { active: true });

    if (query.category === 'saved') {
      if (!viewerId) return ok('Danh sách bài viết đã lưu', empty);
      qb.innerJoin(
        CommunitySaveEntity,
        'save',
        'save.postId = post.id AND save.userId = :viewerId',
        { viewerId },
      );
    } else if (query.category === 'hot') {
      qb.andWhere('(post.category = :hot OR post.likesCount >= 50)', {
        hot: 'hot',
      });
    } else if (query.category && query.category !== 'all') {
      qb.andWhere('post.category = :category', { category: query.category });
    }

    if (query.sector && query.sector !== 'all') {
      qb.andWhere('post.sector = :sector', { sector: query.sector });
    }
    if (query.symbol) {
      qb.andWhere('post.symbol = :symbol', {
        symbol: query.symbol.toUpperCase(),
      });
    }
    if (query.authorId) {
      qb.andWhere('post.userId = :authorId', { authorId: query.authorId });
    }
    const keyword = query.keyword?.trim().toLowerCase();
    if (keyword) {
      qb.andWhere(
        '(LOWER(post.title) LIKE :kw OR LOWER(post.content) LIKE :kw OR LOWER(post.symbol) LIKE :kw OR LOWER(post.authorName) LIKE :kw)',
        { kw: `%${keyword}%` },
      );
    }

    const [posts, total] = await qb
      .orderBy('post.createdAt', 'DESC')
      .skip((page - 1) * limit)
      .take(limit)
      .getManyAndCount();

    if (posts.length === 0) {
      return ok('Danh sách bài viết', { ...empty, total });
    }

    const postIds = posts.map((p) => p.id);
    const [comments, likedIds, savedIds] = await Promise.all([
      this.commentRepo.find({
        where: { postId: In(postIds), active: true },
        order: { createdAt: 'ASC' },
      }),
      this.viewerPostIds(this.likeRepo, postIds, viewerId),
      this.viewerPostIds(this.saveRepo, postIds, viewerId),
    ]);

    const commentsByPost = new Map<number, CommentView[]>();
    for (const comment of comments) {
      const list = commentsByPost.get(comment.postId) ?? [];
      list.push(toCommentView(comment));
      commentsByPost.set(comment.postId, list);
    }

    return ok('Danh sách bài viết thành công', {
      posts: posts.map((post) =>
        toPostView(post, commentsByPost.get(post.id) ?? [], {
          isLiked: likedIds.has(post.id),
          isSaved: savedIds.has(post.id),
        }),
      ),
      total,
      page,
      limit,
    });
  }

  async createPost(dto: CreateCommunityPostDto, authUser: AuthUser) {
    const author = toCommunityMember(await this.findMember(authUser.id));

    const saved = await this.postRepo.save(
      this.postRepo.create({
        userId: author.id,
        authorName: author.name,
        authorAvatar: author.avatar ?? undefined,
        authorRole: author.role,
        authorBadge: author.badge,
        title: dto.title || undefined,
        content: dto.content,
        symbol: dto.symbol || undefined,
        stance: dto.stance ?? 'ANALYSIS',
        targetPrice: dto.targetPrice,
        stopLossPrice: dto.stopLossPrice,
        category: dto.category ?? 'hot',
        sector: dto.sector,
        imageUrl: dto.imageUrl,
        likesCount: 1, // the author likes their own post
        commentsCount: 0,
        viewsCount: 1,
        createdBy: author.id,
      }),
    );
    await this.likeRepo.save({ postId: saved.id, userId: author.id });

    // Everyone else receives the post as "not liked/saved by me".
    this.realtime.broadcast(
      ServerEvent.POST_CREATED,
      toPostView(saved, [], { isLiked: false, isSaved: false }),
    );

    return ok(
      'Đăng bài viết thành công',
      toPostView(saved, [], { isLiked: true, isSaved: false }),
    );
  }

  async toggleLike(postId: number, userId: number) {
    await this.findPost(postId);

    const existing = await this.likeRepo.findOne({ where: { postId, userId } });
    if (existing) {
      await this.likeRepo.remove(existing);
      await this.postRepo
        .createQueryBuilder()
        .update()
        .set({ likesCount: () => 'GREATEST("likesCount" - 1, 0)' })
        .where('id = :postId', { postId })
        .execute();
    } else {
      await this.likeRepo.save({ postId, userId });
      await this.postRepo.increment({ id: postId }, 'likesCount', 1);
    }

    const { likesCount } = await this.findPost(postId);
    const isLiked = !existing;

    this.realtime.broadcast(ServerEvent.POST_LIKES, {
      postId: String(postId),
      likesCount,
    });

    return ok(isLiked ? 'Đã thả tim bài viết' : 'Đã bỏ tim bài viết', {
      isLiked,
      likesCount,
    });
  }

  async toggleSave(postId: number, userId: number) {
    await this.findPost(postId);

    const existing = await this.saveRepo.findOne({ where: { postId, userId } });
    if (existing) {
      await this.saveRepo.remove(existing);
    } else {
      await this.saveRepo.save({ postId, userId });
    }

    const isSaved = !existing;
    return ok(
      isSaved
        ? 'Đã lưu bài viết vào danh sách quan tâm'
        : 'Đã hủy lưu bài viết',
      { isSaved },
    );
  }

  async addComment(
    postId: number,
    dto: CreateCommunityCommentDto,
    authUser: AuthUser,
  ) {
    await this.findPost(postId);
    const author = toCommunityMember(await this.findMember(authUser.id));

    const saved = await this.commentRepo.save(
      this.commentRepo.create({
        postId,
        userId: author.id,
        authorName: author.name,
        authorAvatar: author.avatar ?? undefined,
        content: dto.content,
        likesCount: 0,
        createdBy: author.id,
      }),
    );
    await this.postRepo.increment({ id: postId }, 'commentsCount', 1);

    const comment = toCommentView(saved);
    this.realtime.broadcast(ServerEvent.COMMENT_CREATED, comment);

    return ok('Đã gửi bình luận thành công', comment);
  }

  async deleteComment(commentId: number, authUser: AuthUser) {
    const comment = await this.commentRepo.findOne({
      where: { id: commentId },
    });
    if (!comment) throw new NotFoundException('Bình luận không tồn tại');
    this.assertCanModify(comment.userId, authUser, 'bình luận');

    await this.commentRepo.update(commentId, { deletedBy: authUser.id });
    await this.commentRepo.softDelete(commentId);
    await this.postRepo
      .createQueryBuilder()
      .update()
      .set({ commentsCount: () => 'GREATEST("commentsCount" - 1, 0)' })
      .where('id = :postId', { postId: comment.postId })
      .execute();

    this.realtime.broadcast(ServerEvent.COMMENT_DELETED, {
      postId: String(comment.postId),
      commentId: String(commentId),
    });

    return ok('Đã xóa bình luận', null);
  }

  async deletePost(postId: number, authUser: AuthUser) {
    const post = await this.findPost(postId);
    this.assertCanModify(post.userId, authUser, 'bài viết');

    await this.postRepo.update(postId, { deletedBy: authUser.id });
    await this.postRepo.softDelete(postId);

    this.realtime.broadcast(ServerEvent.POST_DELETED, {
      postId: String(postId),
    });

    return ok('Đã xóa bài viết', null);
  }

  private async findPost(postId: number) {
    const post = await this.postRepo.findOne({ where: { id: postId } });
    if (!post) throw new NotFoundException('Bài viết không tồn tại');
    return post;
  }

  private async findMember(userId: number) {
    const user = await this.usersRepo.findOne({
      where: { id: userId },
      select: MEMBER_COLUMNS,
    });
    if (!user) throw new NotFoundException('Tài khoản không tồn tại');
    return user;
  }

  /** Only the author or an administrator may change a post or comment. */
  private assertCanModify(
    ownerId: number | null | undefined,
    authUser: AuthUser,
    what: string,
  ) {
    const isOwner = ownerId != null && ownerId === authUser.id;
    if (!isOwner && authUser.role !== UserRole.ADMIN) {
      throw new ForbiddenException(`Bạn không có quyền xóa ${what} này`);
    }
  }

  private async viewerPostIds(
    repo: Repository<CommunityLikeEntity | CommunitySaveEntity>,
    postIds: number[],
    viewerId?: number,
  ): Promise<Set<number>> {
    if (!viewerId) return new Set();
    const rows = await repo.find({
      where: { postId: In(postIds), userId: viewerId, active: true },
      select: ['postId'],
    });
    return new Set(rows.map((row) => row.postId));
  }
}
