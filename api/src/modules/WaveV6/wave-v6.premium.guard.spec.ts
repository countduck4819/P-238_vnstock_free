import { BadGatewayException, ForbiddenException } from '@nestjs/common';
import { AccountType, UserRole } from 'src/shared';
import { WaveV6PremiumGuard } from './wave-v6.premium.guard';
import { WaveV6Service } from './wave-v6.service';

function executionContext(user: unknown): any {
  return { switchToHttp: () => ({ getRequest: () => ({ user }) }) };
}

describe('WaveV6PremiumGuard', () => {
  const guard = new WaveV6PremiumGuard();

  it('allows Premium users and administrators only', () => {
    expect(
      guard.canActivate(
        executionContext({ role: UserRole.USER, accountType: AccountType.PREMIUM }),
      ),
    ).toBe(true);
    expect(guard.canActivate(executionContext({ role: UserRole.ADMIN }))).toBe(true);
    expect(() =>
      guard.canActivate(
        executionContext({ role: UserRole.USER, accountType: AccountType.FREE }),
      ),
    ).toThrow(ForbiddenException);
  });
});

describe('WaveV6Service', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    process.env.PYTHON_API_URL = 'http://python_data:6060/api';
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it('accepts only the independent advisory contract from Python', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        trade_authorized: false,
        advisory: { independent_from_h120: true },
        predictions: [{ symbol: 'FPT' }],
      }),
    });
    await expect(new WaveV6Service().latest(10)).resolves.toMatchObject({
      trade_authorized: false,
    });
    expect(global.fetch).toHaveBeenCalledWith(
      'http://python_data:6060/api/wave-v6/latest?limit=10',
      expect.objectContaining({ headers: { accept: 'application/json' } }),
    );
  });

  it('rejects a payload that is combined with H120', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        trade_authorized: false,
        advisory: { independent_from_h120: false },
        predictions: [],
      }),
    });
    await expect(new WaveV6Service().latest(10)).rejects.toBeInstanceOf(
      BadGatewayException,
    );
  });
});
