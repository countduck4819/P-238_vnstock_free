import { UnauthorizedException } from '@nestjs/common';
import { AuthGuard } from '@nestjs/passport';
import { JwtAuthGuard } from './jwt-auth.guard';

const passportCanActivate = jest.spyOn(
  AuthGuard('jwt').prototype,
  'canActivate',
);

function setup(isPublic: boolean, authorization?: string) {
  const request: { headers: Record<string, string>; user?: unknown } = {
    headers: authorization ? { authorization } : {},
  };
  const reflector = { getAllAndOverride: jest.fn().mockReturnValue(isPublic) };
  const context = {
    getHandler: jest.fn(),
    getClass: jest.fn(),
    switchToHttp: () => ({ getRequest: () => request }),
  };
  return {
    guard: new JwtAuthGuard(reflector as any),
    context: context as any,
    request,
  };
}

describe('JwtAuthGuard', () => {
  afterEach(() => passportCanActivate.mockReset());

  it('requires a valid token on protected routes', async () => {
    passportCanActivate.mockRejectedValue(new UnauthorizedException());
    const { guard, context } = setup(false, 'Bearer bad');

    await expect(guard.canActivate(context)).rejects.toThrow(
      UnauthorizedException,
    );
  });

  it('lets guests through public routes without touching passport', async () => {
    const { guard, context } = setup(true);

    await expect(guard.canActivate(context)).resolves.toBe(true);
    expect(passportCanActivate).not.toHaveBeenCalled();
  });

  it('resolves the user on public routes when a token is sent', async () => {
    passportCanActivate.mockResolvedValue(true);
    const { guard, context } = setup(true, 'Bearer good');

    await expect(guard.canActivate(context)).resolves.toBe(true);
    expect(passportCanActivate).toHaveBeenCalledTimes(1);
  });

  it('ignores an invalid token on public routes', async () => {
    passportCanActivate.mockRejectedValue(new UnauthorizedException());
    const { guard, context, request } = setup(true, 'Bearer expired');

    await expect(guard.canActivate(context)).resolves.toBe(true);
    expect(request.user).toBeUndefined();
  });
});
