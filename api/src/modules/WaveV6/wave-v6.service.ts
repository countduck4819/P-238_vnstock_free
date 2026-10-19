import {
  BadGatewayException,
  Injectable,
  ServiceUnavailableException,
} from '@nestjs/common';
import * as fs from 'fs';
import * as path from 'path';

type V6Payload = {
  trend_type: 'long_term';
  as_of_date: string;
  snapshot_date: string;
  trade_authorized: false;
  advisory: {
    fixed_horizon_sessions: null;
    advisory_only: true;
    not_a_trade_instruction: true;
    independent_from_h120: true;
  };
  summary: { eligible_rows?: number; shortlist_rows?: number };
  predictions: unknown[];
  [key: string]: unknown;
};

function symbolsDate(top50: { symbols?: Array<{ date?: string }> }): string {
  return top50.symbols?.find((item) => item?.date)?.date ?? '';
}

@Injectable()
export class WaveV6Service {
  private readonly timeoutMs = Number(
    process.env.WAVE_V6_UPSTREAM_TIMEOUT_MS ?? 5_000,
  );

  // Dài hạn cập nhật bằng cách chép hai file mới vào predict_xgboost_and_lstm/:
  // ensemble_top50_stocks.json (xếp hạng) và predict_top50_stocks.json (LSTM).
  private findPredictionDir(): string | null {
    const candidates = [
      path.resolve(process.cwd(), 'predict_xgboost_and_lstm'),
      path.resolve(process.cwd(), '../predict_xgboost_and_lstm'),
      '/app/predict_xgboost_and_lstm',
    ];
    for (const c of candidates) {
      if (fs.existsSync(c)) return c;
    }
    return null;
  }

  private loadDirectPayload(limit = 50): V6Payload | null {
    try {
      const predictionDir = this.findPredictionDir();
      if (!predictionDir) return null;

      const top50Path = path.join(predictionDir, 'ensemble_top50_stocks.json');
      const pricePath = path.join(predictionDir, 'predict_top50_stocks.json');

      if (!fs.existsSync(top50Path)) return null;

      const top50 = JSON.parse(fs.readFileSync(top50Path, 'utf8'));
      let prices: Record<string, any> = {};
      if (fs.existsSync(pricePath)) {
        try {
          prices = JSON.parse(fs.readFileSync(pricePath, 'utf8'));
        } catch {
          // ignore
        }
      }

      const asOfDate = top50.as_of_date || symbolsDate(top50);
      const symbols = Array.isArray(top50.symbols) ? top50.symbols : [];
      const sliced = symbols.slice(0, limit);

      const predictions = sliced.map((item: any) => {
        const ticker = String(item.ticker || item.symbol || '').toUpperCase();
        const priceInfo = prices[ticker];
        let priceForecast: any = null;

        if (priceInfo && Array.isArray(priceInfo.future) && priceInfo.future.length > 0) {
          const lastPoint = priceInfo.future[priceInfo.future.length - 1];
          priceForecast = {
            last_close_price: Number(priceInfo.last_close_price) || 0,
            predicted_price: Number(lastPoint?.predicted_close) || 0,
            forecast_horizon_sessions: priceInfo.future.length,
            forecast: priceInfo.future,
            as_of_date: asOfDate,
            chart_path: priceInfo.chart_path || null,
          };
        }

        return {
          symbol: ticker,
          date: item.date || asOfDate,
          long_term_rank: item.rank || 1,
          long_term_trend_probability:
            typeof item.p_ensemble === 'number' ? item.p_ensemble : null,
          price_forecast: priceForecast,
        };
      });

      return {
        trend_type: 'long_term',
        as_of_date: asOfDate,
        snapshot_date: top50.snapshot_date || asOfDate,
        trade_authorized: false,
        advisory: {
          fixed_horizon_sessions: null,
          advisory_only: true,
          not_a_trade_instruction: true,
          independent_from_h120: true,
        },
        summary: {
          eligible_rows:
            Number(top50.source_prediction_output?.rows) || symbols.length,
          shortlist_rows: symbols.length,
        },
        predictions,
      };
    } catch {
      return null;
    }
  }

  private upstreamUrl(pathStr: string): string {
    const baseUrl = process.env.PYTHON_API_URL?.replace(/\/+$/, '');
    if (!baseUrl) {
      throw new ServiceUnavailableException(
        'Long-term advisory service is not configured.',
      );
    }
    return `${baseUrl}/wave-v6${pathStr}`;
  }

  private async get(pathStr: string): Promise<V6Payload> {
    let response: Response;
    try {
      response = await fetch(this.upstreamUrl(pathStr), {
        signal: AbortSignal.timeout(this.timeoutMs),
        headers: { accept: 'application/json' },
      });
    } catch {
      throw new ServiceUnavailableException(
        'Long-term advisory service is temporarily unavailable.',
      );
    }

    let payload: V6Payload | undefined;
    try {
      payload = (await response.json()) as V6Payload;
    } catch {
      throw new BadGatewayException(
        'Long-term advisory service returned an invalid response.',
      );
    }
    if (!response.ok) {
      throw new ServiceUnavailableException(
        'Long-term advisory data is temporarily unavailable.',
      );
    }
    if (
      payload.trade_authorized !== false ||
      payload.advisory?.independent_from_h120 !== true ||
      !Array.isArray(payload.predictions)
    ) {
      throw new BadGatewayException(
        'Long-term advisory contract validation failed.',
      );
    }
    return payload;
  }

  async latest(limit: number): Promise<V6Payload> {
    const local = this.loadDirectPayload(limit);
    if (local && local.predictions.length > 0) {
      return local;
    }
    return this.get(`/latest?limit=${limit}`);
  }

  async bySymbol(symbol: string): Promise<V6Payload> {
    const local = this.loadDirectPayload(50);
    if (local && local.predictions.length > 0) {
      const match = (local.predictions as any[]).filter(
        (p) => String(p.symbol).toUpperCase() === symbol.toUpperCase(),
      );
      if (match.length > 0) {
        return {
          ...local,
          predictions: match,
        };
      }
    }
    return this.get(`/${encodeURIComponent(symbol)}`);
  }
}
