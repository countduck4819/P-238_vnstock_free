import {
  Entity,
  Column,
  ManyToOne,
  JoinColumn,
} from 'typeorm';
import { IndustryEntity } from '../Industries/industries.entities';
import { BaseEntities } from '../Base/base.entities';

@Entity('stocks')
export class StockEntity extends BaseEntities {
  @Column()
  code: string;

  @Column()
  name: string;

  // @Column({ nullable: true })
  // exchange: string; // Sàn (HOSE, HNX, UPCOM...)

  // @Column({ nullable: true, type: 'decimal', precision: 18, scale: 2 })
  // marketCap: number; // Vốn hóa

  @ManyToOne(() => IndustryEntity, (industry) => industry.stocks)
  @JoinColumn({ name: 'industryId' })
  industry: IndustryEntity;

  @Column({ name: 'industryId', nullable: false })
  industryId: number;
}
