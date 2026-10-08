import { Column, Entity, Index } from 'typeorm';
import { BaseEntities } from '../Base/base.entities';

@Entity('community_posts')
export class CommunityPostEntity extends BaseEntities {
  @Column({ type: 'int', nullable: true })
  @Index()
  userId?: number;

  @Column({ type: 'varchar', length: 255 })
  authorName: string;

  @Column({ type: 'text', nullable: true })
  authorAvatar?: string;

  @Column({ type: 'varchar', length: 100, nullable: true })
  authorRole?: string;

  @Column({ type: 'varchar', length: 50, default: 'Thành viên' })
  authorBadge: string;

  @Column({ type: 'varchar', length: 255, nullable: true })
  title?: string;

  @Column({ type: 'text' })
  content: string;

  @Column({ type: 'varchar', length: 20, nullable: true })
  @Index()
  symbol?: string;

  @Column({ type: 'varchar', length: 20, default: 'ANALYSIS' })
  stance: string; // 'BUY' | 'SELL' | 'HOLD' | 'ANALYSIS'

  @Column({ type: 'float', nullable: true })
  targetPrice?: number;

  @Column({ type: 'float', nullable: true })
  stopLossPrice?: number;

  @Column({ type: 'varchar', length: 50, default: 'hot' })
  @Index()
  category: string; // 'hot' | 'signal' | 'technical' | 'fundamental' | 'qa'

  @Column({ type: 'varchar', length: 100, nullable: true })
  sector?: string;

  @Column({ type: 'text', nullable: true })
  imageUrl?: string;

  @Column({ type: 'int', default: 0 })
  likesCount: number;

  @Column({ type: 'int', default: 0 })
  commentsCount: number;

  @Column({ type: 'int', default: 0 })
  viewsCount: number;
}

@Entity('community_comments')
export class CommunityCommentEntity extends BaseEntities {
  @Column({ type: 'int' })
  @Index()
  postId: number;

  @Column({ type: 'int', nullable: true })
  userId?: number;

  @Column({ type: 'varchar', length: 255 })
  authorName: string;

  @Column({ type: 'text', nullable: true })
  authorAvatar?: string;

  @Column({ type: 'text' })
  content: string;

  @Column({ type: 'int', default: 0 })
  likesCount: number;
}

@Entity('community_likes')
@Index(['postId', 'userId'], { unique: true })
export class CommunityLikeEntity extends BaseEntities {
  @Column({ type: 'int' })
  postId: number;

  @Column({ type: 'int' })
  userId: number;
}

@Entity('community_saves')
@Index(['postId', 'userId'], { unique: true })
export class CommunitySaveEntity extends BaseEntities {
  @Column({ type: 'int' })
  postId: number;

  @Column({ type: 'int' })
  userId: number;
}
