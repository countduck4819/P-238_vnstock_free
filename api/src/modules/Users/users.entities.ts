import { Column, Entity } from "typeorm";
import { BaseEntities } from "../Base/base.entities";
import { AccountType, Gender, UserRole } from "src/shared";

@Entity("users")
export class UsersEntities extends BaseEntities {
  @Column({ length: 50 })
  username: string;

  @Column({ length: 100 })
  email: string;

  @Column({ type: "text" })
  address?: string;

  @Column({ name: "password", type: "text" })
  password: string;

  @Column({ name: "fullName", length: 100, nullable: true })
  fullName?: string;

  @Column({
    name: "role",
    type: "enum",
    enum: UserRole,
    default: UserRole.USER,
  })
  role?: UserRole;

  @Column({
    name: "accountType",
    type: "enum",
    enum: AccountType,
    default: AccountType.FREE,
  })
  accountType?: AccountType;

  @Column({ name: "avatar", type: "text", nullable: true })
  avatar?: string;

  @Column({
    type: "enum",
    enum: Gender,
    nullable: true,
  })
  gender?: Gender;

  @Column({ name: "citizenId", length: 20, unique: true, nullable: true })
  citizenId?: string;

  @Column({
    name: "watchList",
    type: "jsonb",
    default: () => "'[]'",
  })
  watchList: string[];

  @Column({
    name: "refreshToken",
    select: false,
    nullable: true,
    type: "varchar",
  })
  refreshToken?: string | null;
}
