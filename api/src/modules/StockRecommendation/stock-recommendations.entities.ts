import { Entity, Column, ManyToOne, JoinColumn } from 'typeorm';
import { BaseEntities } from '../Base/base.entities';
import { StockEntity } from '../Stocks/stocks.entities';
import { StockRecommendationStatus } from 'src/shared';

@Entity('stock_recommendations')
export class StockRecommendationEntity extends BaseEntities {
  @ManyToOne(() => StockEntity, { eager: true, onDelete: 'CASCADE' })
  @JoinColumn({ name: 'stockId' })
  stock: StockEntity;

  @Column()
  stockId: number;

  @Column({ type: 'decimal', precision: 18, scale: 2 })
  buyPrice: number;

  @Column({ type: 'decimal', precision: 18, scale: 2 })
  targetPrice: number;

  @Column({ type: 'decimal', precision: 18, scale: 2 })
  stopLossPrice: number;

  @Column({
    type: 'enum',
    enum: StockRecommendationStatus,
    default: StockRecommendationStatus.ACTIVE,
  })
  status: StockRecommendationStatus;

  @Column({ nullable: true })
  note?: string;

  @Column({ default: true })
  isActive: boolean;

  @Column({ type: 'timestamp', nullable: true })
  closedAt?: Date;
}
