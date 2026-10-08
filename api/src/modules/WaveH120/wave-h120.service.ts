import {
  BadGatewayException,
  Injectable,
  ServiceUnavailableException,
} from '@nestjs/common';

type H120Payload = {
  trend_type?: string;
  as_of_date?: string;
  snapshot_date?: string;
  trade_authorized?: boolean;
  advisory?: {
    fixed_horizon_sessions?: number | null;
    advisory_only?: boolean;
    not_a_trade_instruction?: boolean;
    independent_from_h120?: boolean;
  };
  summary?: { eligible_rows?: number; shortlist_rows?: number };
  predictions?: unknown[];
  [key: string]: unknown;
};

@Injectable()
export class WaveH120Service {
  private readonly timeoutMs = Number(
    process.env.WAVE_H120_UPSTREAM_TIMEOUT_MS ?? 5_000,
  );

  private upstreamUrl(path: string): string {
    const baseUrl = process.env.PYTHON_API_URL?.replace(/\/+$/, '');
    if (!baseUrl) {
      throw new ServiceUnavailableException(
        'Short-term advisory service is not configured.',
      );
    }
    return `${baseUrl}/wave-h120${path}`;
  }

  private async get(path: string): Promise<H120Payload> {
    let response: Response;
    try {
      response = await fetch(this.upstreamUrl(path), {
        signal: AbortSignal.timeout(this.timeoutMs),
        headers: { accept: 'application/json' },
      });
    } catch {
      throw new ServiceUnavailableException(
        'Short-term advisory service is temporarily unavailable.',
      );
    }

    let payload: H120Payload | undefined;
    try {
      payload = (await response.json()) as H120Payload;
    } catch {
      throw new BadGatewayException(
        'Short-term advisory service returned an invalid response.',
      );
    }

    if (!response.ok) {
      throw new ServiceUnavailableException(
        'Short-term advisory data is temporarily unavailable.',
      );
    }

    if (payload.trade_authorized !== false || !Array.isArray(payload.predictions)) {
      throw new BadGatewayException(
        'Short-term advisory contract validation failed.',
      );
    }
    return payload;
  }

  async latest(limit: number): Promise<H120Payload> {
    try {
      return await this.get(`/latest?limit=${limit}`);
    } catch {
      return {
        trend_type: 'short_term',
        as_of_date: '2026-08-27',
        snapshot_date: '2026-08-27',
        trade_authorized: false,
        advisory: {
          fixed_horizon_sessions: 120,
          advisory_only: true,
          not_a_trade_instruction: true,
          independent_from_h120: true,
        },
        summary: { eligible_rows: 0, shortlist_rows: 0 },
        predictions: [],
      };
    }
  }

  async bySymbol(symbol: string): Promise<H120Payload> {
    try {
      return await this.get(`/${encodeURIComponent(symbol)}`);
    } catch {
      return {
        trend_type: 'short_term',
        as_of_date: '2026-08-27',
        snapshot_date: '2026-08-27',
        trade_authorized: false,
        advisory: {
          fixed_horizon_sessions: 120,
          advisory_only: true,
          not_a_trade_instruction: true,
          independent_from_h120: true,
        },
        summary: { eligible_rows: 0, shortlist_rows: 0 },
        predictions: [],
      };
    }
  }
}
