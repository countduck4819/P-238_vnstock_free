import { createParamDecorator, ExecutionContext } from '@nestjs/common';
import { AccountType, UserRole } from '../enum/TypeEnum.enum';

/** Identity resolved from the access token by `JwtStrategy.validate`. */
export interface AuthUser {
  id: number;
  email: string;
  role: UserRole;
  accountType: AccountType;
}

/**
 * Injects the authenticated user. On `@Public()` routes it is `undefined`
 * when the request carries no valid token.
 */
export const CurrentUser = createParamDecorator(
  (_data: unknown, context: ExecutionContext): AuthUser | undefined =>
    context.switchToHttp().getRequest<{ user?: AuthUser }>().user,
);
