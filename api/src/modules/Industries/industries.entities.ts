import { Entity, Column, OneToMany } from 'typeorm';
import { BaseEntities } from '../Base/base.entities';
import { StockEntity } from '../Stocks/stocks.entities';

@Entity('industries')
export class IndustryEntity extends BaseEntities {
  @Column({ unique: true })
  name: string;

  @OneToMany(() => StockEntity, (stock) => stock.industry, {
    cascade: true,
    onDelete: 'CASCADE',
  })
  stocks: StockEntity[];
}
