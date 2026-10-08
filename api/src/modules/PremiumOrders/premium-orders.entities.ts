import { Entity, Column, ManyToOne, JoinColumn } from 'typeorm';
import { BaseEntities } from '../Base/base.entities';
import { PremiumOrderStatus } from 'src/shared';
import { UsersEntities } from '../Users/users.entities';

@Entity('premium_orders')
export class PremiumOrderEntity extends BaseEntities {
  @Column({ unique: true })
  orderCode: string;

  @Column()
  userId: number;

  @Column()
  amount?: number;

  @Column({
    type: 'enum',
    enum: PremiumOrderStatus,
    default: PremiumOrderStatus.PENDING,
  })
  status: PremiumOrderStatus;

  @Column({ nullable: true })
  transactionId?: string;

  @Column({ nullable: true })
  paymentMethod?: string;

  @ManyToOne(() => UsersEntities, { eager: true })
  @JoinColumn({ name: 'userId' })
  user: UsersEntities;
}
