import { Entity, Column } from 'typeorm';
import { BaseEntities } from '../Base/base.entities';

@Entity('stock_predictions')
export class StockPredictionEntity extends BaseEntities {
  @Column({ type: 'varchar', length: 20 })
  ticker: string;

  @Column({ type: 'float' })
  lastClosePrice: number;

  @Column({ type: 'float' })
  predictedPrice: number;

  @Column({ name: 'p_ensemble', type: 'double precision', nullable: true })
  pEnsemble: number | null;

  @Column({ type: 'varchar', length: 255, nullable: true })
  chartPath: string | null;

  @Column({ type: 'timestamp' })
  predictedOn: Date;
}
