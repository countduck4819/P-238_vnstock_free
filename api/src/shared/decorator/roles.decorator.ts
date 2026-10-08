import { SetMetadata } from '@nestjs/common';
import { AccountType, UserRole } from '../enum/TypeEnum.enum';

export const ROLES_GUARD_KEY = Symbol('roles-guard');
export const Roles = (...values: (UserRole | AccountType)[]) =>
  SetMetadata(ROLES_GUARD_KEY, values);
