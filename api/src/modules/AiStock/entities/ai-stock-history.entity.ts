import { Column, Entity } from 'typeorm';
import { BaseEntities } from 'src/modules/Base/base.entities';

@Entity('ai_stock_history')
export class AiStockHistoryEntity extends BaseEntities {
  @Column({ type: 'int' })
  userId: number;

  @Column({ type: 'text' })
  question: string;

  @Column({ type: 'text', nullable: true })
  answer: string | null;

  @Column({ type: 'varchar', length: 10, nullable: true })
  symbol: string | null;
}
