import {
  Column,
  CreateDateColumn,
  DeleteDateColumn,
  PrimaryGeneratedColumn,
  UpdateDateColumn,
} from "typeorm";

export class BaseEntities {
  @PrimaryGeneratedColumn()
  id: number;

  @CreateDateColumn({ name: "createdAt", type: "timestamp", precision: 6 })
  createdAt: Date;

  @Column({ name: "createdBy", nullable: true })
  createdBy: number;

  @UpdateDateColumn({
    name: "modifiedAt",
    type: "timestamp",
    precision: 6,
    nullable: true,
  })
  modifiedAt: Date;

  @Column({ name: "modifiedBy", nullable: true })
  modifiedBy: number;

  @DeleteDateColumn({
    name: "deletedAt",
    type: "timestamp",
    precision: 6,
    nullable: true,
  })
  deletedAt: Date;

  @Column({ name: "deletedBy", nullable: true })
  deletedBy: number;

  @Column({ default: true })
  active: boolean;
}
