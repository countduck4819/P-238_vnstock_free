import { Column, Entity } from 'typeorm';
import { BaseEntities } from '../Base/base.entities';

@Entity('news')
export class NewsEntity extends BaseEntities {
  @Column({ unique: true })
  news_id: string;

  @Column({ type: 'text' })
  news_title: string;

  @Column({ type: 'text', nullable: true })
  news_sub_title?: string;

  @Column({ type: 'text', nullable: true })
  news_short_content?: string;

  @Column({ type: 'text', nullable: true })
  news_full_content?: string;

  @Column({ type: 'text', nullable: true })
  news_image_url?: string;

  @Column({ type: 'text', nullable: true })
  news_source_link?: string;

  @Column({ type: 'varchar', length: 255, nullable: true })
  public_date?: string;

  @Column({ type: 'varchar', length: 255, nullable: true })
  slug?: string;

  @Column({ type: 'varchar', length: 20, nullable: true })
  symbol?: string;
}
