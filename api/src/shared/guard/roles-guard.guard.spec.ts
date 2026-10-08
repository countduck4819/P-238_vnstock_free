import { ForbiddenException } from '@nestjs/common';
import { AccountType, UserRole } from '../enum/TypeEnum.enum';
import { RolesGuard } from './roles-guard.guard';

function guardFor(
  metadata: (UserRole | AccountType)[],
  user: { role: UserRole; accountType: AccountType } | undefined,
) {
  const reflector = {
    getAllAndOverride: jest
      .fn()
      .mockReturnValueOnce(false)
      .mockReturnValueOnce(metadata),
  };
  const context = {
    getHandler: jest.fn(),
    getClass: jest.fn(),
    switchToHttp: () => ({ getRequest: () => ({ user }) }),
  };
  return { guard: new RolesGuard(reflector as any), context: context as any };
}

describe('RolesGuard', () => {
  it('allows a premium user through a premium-only endpoint', () => {
    const { guard, context } = guardFor([AccountType.PREMIUM], {
      role: UserRole.USER,
      accountType: AccountType.PREMIUM,
    });

    expect(guard.canActivate(context)).toBe(true);
  });

  it('rejects a free user from a premium-only endpoint', () => {
    const { guard, context } = guardFor([AccountType.PREMIUM], {
      role: UserRole.USER,
      accountType: AccountType.FREE,
    });

    expect(() => guard.canActivate(context)).toThrow(ForbiddenException);
  });

  it('requires both role and account type when both are declared', () => {
    const { guard, context } = guardFor(
      [UserRole.USER, AccountType.PREMIUM],
      { role: UserRole.USER, accountType: AccountType.FREE },
    );

    expect(() => guard.canActivate(context)).toThrow(ForbiddenException);
  });

  it('keeps administrator access', () => {
    const { guard, context } = guardFor([AccountType.PREMIUM], {
      role: UserRole.ADMIN,
      accountType: AccountType.FREE,
    });

    expect(guard.canActivate(context)).toBe(true);
  });
});
