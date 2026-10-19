import { UserRole } from 'src/shared';
import { UsersEntities } from '../Users/users.entities';

/** Public view of a member: safe to show to any other user. */
export interface CommunityMember {
  id: number;
  name: string;
  avatar: string | null;
  role: string;
  badge: string;
}

export function toCommunityMember(user: UsersEntities): CommunityMember {
  const isAdmin = user.role === UserRole.ADMIN;
  return {
    id: user.id,
    name: user.fullName?.trim() || user.username,
    avatar: user.avatar ?? null,
    role: isAdmin ? 'Quản trị viên FinSight' : 'Hội viên FinSight',
    badge: isAdmin ? 'Chuyên gia' : 'Thành viên',
  };
}

/** Columns needed to build a `CommunityMember`, never secrets. */
export const MEMBER_COLUMNS: (keyof UsersEntities)[] = [
  'id',
  'username',
  'fullName',
  'avatar',
  'role',
];
