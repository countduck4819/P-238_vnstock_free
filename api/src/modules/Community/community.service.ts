import {
  Inject,
  Injectable,
  Logger,
  NotFoundException,
  OnModuleInit,
} from '@nestjs/common';
import { Repository, Like, In } from 'typeorm';
import {
  CommunityPostEntity,
  CommunityCommentEntity,
  CommunityLikeEntity,
  CommunitySaveEntity,
} from './community.entities';
import {
  CommunityPostRepository,
  CommunityCommentRepository,
  CommunityLikeRepository,
  CommunitySaveRepository,
  HttpStatusCode,
  ResponseCode,
  BaseResDataI,
} from 'src/shared';
import {
  CreateCommunityPostDto,
  CreateCommunityCommentDto,
  GetCommunityPostsQueryDto,
} from './community.dto';

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
    title: 'Góc nhìn TCB: Động lực tăng trưởng từ CASA và tín dụng Bất động sản',
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
  ) {}

  async onModuleInit() {
    await this.seedInitialPostsIfEmpty();
  }

  private async seedInitialPostsIfEmpty() {
    try {
      const count = await this.postRepo.count();
      if (count === 0) {
        this.logger.log('Seeding initial community posts...');
        for (const postData of SEED_POSTS) {
          const post = this.postRepo.create(postData);
          const saved = await this.postRepo.save(post);

          // Seed 1-2 comments
          if (saved.symbol === 'FPT') {
            await this.commentRepo.save([
              {
                postId: saved.id,
                authorName: 'Trần Minh Quang',
                content:
                  'Đồng quan điểm! Nhịp này FPT tích lũy rất chặt chẽ, target 160k hoàn toàn khả thi.',
                likesCount: 12,
              },
              {
                postId: saved.id,
                authorName: 'Lê Thảo My',
                content:
                  'Khối ngoại vừa gom ròng hơn 150 tỷ phiên hôm qua, xu hướng cực kỳ rõ ràng.',
                likesCount: 5,
              },
            ]);
          } else if (saved.symbol === 'HPG') {
            await this.commentRepo.save({
              postId: saved.id,
              authorName: 'Nguyễn Văn Hùng',
              content:
                'Dung Quất 2 sắp đi vào vận hành sẽ là động lực tăng trưởng lớn cho HPG!',
              likesCount: 8,
            });
          }
        }
        this.logger.log('Seeded initial community posts successfully.');
      }
    } catch (err) {
      this.logger.error('Failed to seed community posts', err);
    }
  }

  async getPosts(
    query: GetCommunityPostsQueryDto,
    currentUserId?: number,
  ): Promise<BaseResDataI<any>> {
    const page = Number(query.page) || 1;
    const limit = Number(query.limit) || 20;
    const skip = (page - 1) * limit;

    const qb = this.postRepo
      .createQueryBuilder('post')
      .where('post.active = :active', { active: true });

    // Category filter
    if (query.category && query.category !== 'all') {
      if (query.category === 'saved') {
        if (!currentUserId) {
          return {
            status: HttpStatusCode.OK,
            code: ResponseCode.SUCCESS,
            message: 'Danh sách bài viết đã lưu',
            data: { posts: [], total: 0, page, limit },
          };
        }

        const userSaves = await this.saveRepo.find({
          where: { userId: currentUserId, active: true },
          select: ['postId'],
        });
        const savedPostIds = userSaves.map((s) => s.postId);

        if (savedPostIds.length === 0) {
          return {
            status: HttpStatusCode.OK,
            code: ResponseCode.SUCCESS,
            message: 'Danh sách bài viết đã lưu',
            data: { posts: [], total: 0, page, limit },
          };
        }

        qb.andWhere('post.id IN (:...savedPostIds)', { savedPostIds });
      } else if (query.category === 'hot') {
        qb.andWhere('(post.category = :cat OR post.likesCount >= 50)', {
          cat: 'hot',
        });
      } else {
        qb.andWhere('post.category = :category', { category: query.category });
      }
    }

    // Sector filter
    if (query.sector && query.sector !== 'all') {
      qb.andWhere('post.sector = :sector', { sector: query.sector });
    }

    // Symbol filter
    if (query.symbol) {
      qb.andWhere('post.symbol = :symbol', {
        symbol: query.symbol.toUpperCase(),
      });
    }

    // Keyword search
    if (query.keyword && query.keyword.trim()) {
      const kw = `%${query.keyword.trim().toLowerCase()}%`;
      qb.andWhere(
        '(LOWER(post.title) LIKE :kw OR LOWER(post.content) LIKE :kw OR LOWER(post.symbol) LIKE :kw OR LOWER(post.authorName) LIKE :kw)',
        { kw },
      );
    }

    qb.orderBy('post.createdAt', 'DESC').skip(skip).take(limit);

    const [posts, total] = await qb.getManyAndCount();

    if (posts.length === 0) {
      return {
        status: HttpStatusCode.OK,
        code: ResponseCode.SUCCESS,
        message: 'Danh sách bài viết',
        data: { posts: [], total, page, limit },
      };
    }

    const postIds = posts.map((p) => p.id);

    // Get comments for all retrieved posts
    const comments = await this.commentRepo.find({
      where: { postId: In(postIds), active: true },
      order: { createdAt: 'ASC' },
    });

    const commentsMap: Record<number, CommunityCommentEntity[]> = {};
    for (const c of comments) {
      if (!commentsMap[c.postId]) {
        commentsMap[c.postId] = [];
      }
      commentsMap[c.postId].push(c);
    }

    // Get isLiked and isSaved if user is logged in
    let likedSet = new Set<number>();
    let savedSet = new Set<number>();

    if (currentUserId) {
      const [likes, saves] = await Promise.all([
        this.likeRepo.find({
          where: { postId: In(postIds), userId: currentUserId, active: true },
          select: ['postId'],
        }),
        this.saveRepo.find({
          where: { postId: In(postIds), userId: currentUserId, active: true },
          select: ['postId'],
        }),
      ]);

      likedSet = new Set(likes.map((l) => l.postId));
      savedSet = new Set(saves.map((s) => s.postId));
    }

    const resultPosts = posts.map((p) => ({
      id: String(p.id),
      userId: p.userId,
      authorName: p.authorName,
      authorAvatar: p.authorAvatar,
      authorRole: p.authorRole,
      authorBadge: p.authorBadge,
      title: p.title,
      content: p.content,
      symbol: p.symbol,
      stance: p.stance,
      targetPrice: p.targetPrice,
      stopLossPrice: p.stopLossPrice,
      category: p.category,
      sector: p.sector,
      imageUrl: p.imageUrl,
      likes: p.likesCount,
      commentsCount: p.commentsCount,
      viewsCount: p.viewsCount,
      isLiked: likedSet.has(p.id),
      isSaved: savedSet.has(p.id),
      createdAt: p.createdAt,
      comments: (commentsMap[p.id] || []).map((c) => ({
        id: String(c.id),
        postId: String(c.postId),
        userId: c.userId,
        authorName: c.authorName,
        authorAvatar: c.authorAvatar,
        content: c.content,
        likes: c.likesCount,
        createdAt: c.createdAt,
      })),
    }));

    return {
      status: HttpStatusCode.OK,
      code: ResponseCode.SUCCESS,
      message: 'Danh sách bài viết thành công',
      data: {
        posts: resultPosts,
        total,
        page,
        limit,
      },
    };
  }

  async createPost(
    dto: CreateCommunityPostDto,
    currentUser?: {
      id?: number;
      fullName?: string;
      username?: string;
      avatar?: string;
      role?: string;
    },
  ): Promise<BaseResDataI<any>> {
    const authorName =
      currentUser?.fullName ||
      currentUser?.username ||
      dto.authorName ||
      'Nhà đầu tư FinSight';
    const authorAvatar = currentUser?.avatar || dto.authorAvatar || null;
    const authorRole =
      currentUser?.role === 'Admin'
        ? 'Quản trị viên FinSight'
        : dto.authorRole || 'Hội viên FinSight';
    const authorBadge =
      currentUser?.role === 'Admin'
        ? 'Chuyên gia'
        : dto.authorBadge || 'Thành viên';

    const post = this.postRepo.create({
      userId: currentUser?.id || dto.userId,
      authorName,
      authorAvatar: authorAvatar || undefined,
      authorRole,
      authorBadge,
      title: dto.title,
      content: dto.content,
      symbol: dto.symbol ? dto.symbol.toUpperCase() : undefined,
      stance: dto.stance || 'ANALYSIS',
      targetPrice: dto.targetPrice,
      stopLossPrice: dto.stopLossPrice,
      category: dto.category || 'hot',
      sector: dto.sector,
      imageUrl: dto.imageUrl,
      likesCount: 1, // Auto-like on create
      commentsCount: 0,
      viewsCount: 1,
    });

    const saved = await this.postRepo.save(post);

    // Auto mark like for creator if userId is present
    if (currentUser?.id || dto.userId) {
      const uId = currentUser?.id || dto.userId;
      if (uId) {
        await this.likeRepo.save({
          postId: saved.id,
          userId: uId,
        });
      }
    }

    return {
      status: HttpStatusCode.OK,
      code: ResponseCode.SUCCESS,
      message: 'Đăng bài viết thành công',
      data: {
        ...saved,
        id: String(saved.id),
        isLiked: true,
        isSaved: false,
        comments: [],
      },
    };
  }

  async toggleLike(
    postId: number,
    userId: number,
  ): Promise<BaseResDataI<{ isLiked: boolean; likesCount: number }>> {
    const post = await this.postRepo.findOne({ where: { id: postId } });
    if (!post) {
      throw new NotFoundException('Bài viết không tồn tại');
    }

    const existingLike = await this.likeRepo.findOne({
      where: { postId, userId },
    });

    let isLiked = false;
    if (existingLike) {
      await this.likeRepo.remove(existingLike);
      post.likesCount = Math.max(0, post.likesCount - 1);
      isLiked = false;
    } else {
      await this.likeRepo.save({ postId, userId });
      post.likesCount += 1;
      isLiked = true;
    }

    await this.postRepo.save(post);

    return {
      status: HttpStatusCode.OK,
      code: ResponseCode.SUCCESS,
      message: isLiked ? 'Đã thả tim bài viết' : 'Đã bỏ tim bài viết',
      data: {
        isLiked,
        likesCount: post.likesCount,
      },
    };
  }

  async toggleSave(
    postId: number,
    userId: number,
  ): Promise<BaseResDataI<{ isSaved: boolean }>> {
    const post = await this.postRepo.findOne({ where: { id: postId } });
    if (!post) {
      throw new NotFoundException('Bài viết không tồn tại');
    }

    const existingSave = await this.saveRepo.findOne({
      where: { postId, userId },
    });

    let isSaved = false;
    if (existingSave) {
      await this.saveRepo.remove(existingSave);
      isSaved = false;
    } else {
      await this.saveRepo.save({ postId, userId });
      isSaved = true;
    }

    return {
      status: HttpStatusCode.OK,
      code: ResponseCode.SUCCESS,
      message: isSaved
        ? 'Đã lưu bài viết vào danh sách quan tâm'
        : 'Đã hủy lưu bài viết',
      data: { isSaved },
    };
  }

  async addComment(
    postId: number,
    dto: CreateCommunityCommentDto,
    currentUser?: {
      id?: number;
      fullName?: string;
      username?: string;
      avatar?: string;
    },
  ): Promise<BaseResDataI<any>> {
    const post = await this.postRepo.findOne({ where: { id: postId } });
    if (!post) {
      throw new NotFoundException('Bài viết không tồn tại');
    }

    const authorName =
      currentUser?.fullName ||
      currentUser?.username ||
      dto.authorName ||
      'Nhà đầu tư FinSight';
    const authorAvatar = currentUser?.avatar || dto.authorAvatar || null;

    const comment = this.commentRepo.create({
      postId,
      userId: currentUser?.id || dto.userId,
      authorName,
      authorAvatar: authorAvatar || undefined,
      content: dto.content,
      likesCount: 0,
    });

    const savedComment = await this.commentRepo.save(comment);

    // Increment post commentsCount
    post.commentsCount += 1;
    await this.postRepo.save(post);

    return {
      status: HttpStatusCode.OK,
      code: ResponseCode.SUCCESS,
      message: 'Đã gửi bình luận thành công',
      data: {
        id: String(savedComment.id),
        postId: String(savedComment.postId),
        userId: savedComment.userId,
        authorName: savedComment.authorName,
        authorAvatar: savedComment.authorAvatar,
        content: savedComment.content,
        likes: savedComment.likesCount,
        createdAt: savedComment.createdAt,
      },
    };
  }

  async deletePost(
    postId: number,
    currentUser?: { id?: number; role?: string },
  ): Promise<BaseResDataI<null>> {
    const post = await this.postRepo.findOne({ where: { id: postId } });
    if (!post) {
      throw new NotFoundException('Bài viết không tồn tại');
    }

    if (
      currentUser?.role !== 'Admin' &&
      post.userId &&
      post.userId !== currentUser?.id
    ) {
      return {
        status: HttpStatusCode.FORBIDDEN,
        code: ResponseCode.ERROR,
        message: 'Bạn không có quyền xóa bài viết này',
        data: null,
      };
    }

    await this.postRepo.softDelete(postId);

    return {
      status: HttpStatusCode.OK,
      code: ResponseCode.SUCCESS,
      message: 'Đã xóa bài viết',
      data: null,
    };
  }
}
