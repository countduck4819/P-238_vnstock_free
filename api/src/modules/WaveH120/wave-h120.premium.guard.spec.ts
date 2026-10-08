import { BadGatewayException, ForbiddenException } from '@nestjs/common';
import { AccountType, UserRole } from 'src/shared';
import { WaveH120PremiumGuard } from './wave-h120.premium.guard';
import { WaveH120Service } from './wave-h120.service';

function executionContext(user: unknown): any {
  return {
    switchToHttp: () => ({
      getRequest: () => ({ user }),
    }),
  };
}

describe('WaveH120PremiumGuard', () => {
  const guard = new WaveH120PremiumGuard();

  it('allows Premium users and administrators only', () => {
    expect(
      guard.canActivate(
        executionContext({
          role: UserRole.USER,
          accountType: AccountType.PREMIUM,
        }),
      ),
    ).toBe(true);
    expect(
      guard.canActivate(executionContext({ role: UserRole.ADMIN })),
    ).toBe(true);
    expect(() =>
      guard.canActivate(
        executionContext({
          role: UserRole.USER,
          accountType: AccountType.FREE,
        }),
      ),
    ).toThrow(ForbiddenException);
  });
});

describe('WaveH120Service', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    process.env.PYTHON_API_URL = 'http://python_data:6060/api';
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it('accepts only the advisory contract from Python', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        trade_authorized: false,
        predictions: [{ symbol: 'MSB' }],
      }),
    });

    await expect(new WaveH120Service().latest(1)).resolves.toMatchObject({
      trade_authorized: false,
    });
    expect(global.fetch).toHaveBeenCalledWith(
      'http://python_data:6060/api/wave-h120/latest?limit=1',
      expect.objectContaining({ headers: { accept: 'application/json' } }),
    );
  });

  it('rejects an upstream response that claims trade authorization', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ trade_authorized: true, predictions: [] }),
    });

    await expect(new WaveH120Service().latest(1)).rejects.toBeInstanceOf(
      BadGatewayException,
    );
  });
});
