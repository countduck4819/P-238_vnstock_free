import { Inject, Injectable, OnModuleInit, Logger } from '@nestjs/common';
import { Repository } from 'typeorm';
import {
  StockPredictionRepository,
  StockPredictionServiceI,
  HttpStatusCode,
  ResponseCode,
  BaseResDataI,
  StockPredictionResI,
} from 'src/shared';
import { BaseServices } from '../Base/base.services';
import { StockPredictionEntity } from './stock-prediction.entities';
import * as fs from 'fs';
import * as path from 'path';

@Injectable()
export class StockPredictionService
  extends BaseServices<StockPredictionEntity>
  implements StockPredictionServiceI, OnModuleInit
{
  private readonly logger = new Logger(StockPredictionService.name);

  // Dài hạn cập nhật bằng cách chép file LSTM mới vào predict_xgboost_and_lstm/.
  private readonly defaultJsonPath = path.resolve(
    process.cwd(),
    '../predict_xgboost_and_lstm/predict_top50_stocks.json',
  );
  private importSignature = '';
  private importing = false;

  constructor(
    @Inject(StockPredictionRepository)
    protected readonly repo: Repository<StockPredictionEntity>,
  ) {
    super(repo);
  }

  /** Khởi chạy server → auto import + theo dõi file */
  onModuleInit() {
    // Importing over the VPS tunnel can take several seconds. Do not block
    // Nest bootstrap (and therefore port 8000) while refreshing predictions.
    setImmediate(() => this.triggerRefresh());
    setInterval(() => this.triggerRefresh(), 3000).unref();
  }

  private triggerRefresh() {
    void this.refreshFromJson().catch((error) => {
      this.logger.error('Failed to refresh stock predictions', error);
    });
  }

  private resolveJsonPath(): string {
    const configured = process.env.LSTM_PRICE_PREDICTION_JSON_PATH;
    if (configured) {
      return path.isAbsolute(configured)
        ? configured
        : path.resolve(process.cwd(), configured);
    }
    return this.defaultJsonPath;
  }

  private async refreshFromJson() {
    if (this.importing) return;
    const currentPath = this.resolveJsonPath();
    let signature = 'missing';
    try {
      const stat = fs.statSync(currentPath);
      signature = `${currentPath}:${stat.size}:${stat.mtimeMs}`;
    } catch {
      return;
    }
    if (signature === this.importSignature) return;
    this.importing = true;
    try {
      const result = await this.importFromJson(currentPath);
      if (result.success) this.importSignature = signature;
    } finally {
      this.importing = false;
    }
  }

  /** Đọc file JSON */
  private readPredictionFile(jsonPath = this.resolveJsonPath()) {
    try {
      if (!fs.existsSync(jsonPath)) return null;
      const raw = fs.readFileSync(jsonPath, 'utf8');
      return JSON.parse(raw);
    } catch (err) {
      this.logger.error('❌ Lỗi đọc file JSON', err);
      return null;
    }
  }

  /** Import từ JSON vào DB */
  private normalizeRows(data: any) {
    const rows: Array<{
      ticker: string;
      lastClosePrice: number;
      predictedPrice: number;
      pEnsemble: number | null;
      chartPath?: string | null;
      predictedOn: Date;
    }> = [];

    if (Array.isArray(data?.predictions)) {
      const predictedOn = new Date(
        data.as_of_date ?? data.generated_at_utc ?? Date.now(),
      );
      for (const item of data.predictions) {
        const forecast = Array.isArray(item?.forecast) ? item.forecast : [];
        const last = forecast.at(-1);
        const ticker = String(item?.symbol ?? '').trim().toUpperCase();
        const lastClosePrice = Number(item?.last_close);
        const predictedPrice = Number(last?.predicted_close);
        const rawPEnsemble = Number(item?.p_ensemble);
        if (
          ticker &&
          Number.isFinite(lastClosePrice) &&
          Number.isFinite(predictedPrice)
        ) {
          rows.push({
            ticker,
            lastClosePrice,
            predictedPrice,
            pEnsemble: Number.isFinite(rawPEnsemble) ? rawPEnsemble : null,
            chartPath: item?.chart_path ?? null,
            predictedOn,
          });
        }
      }
      return rows;
    }

    if (data && typeof data === 'object') {
      for (const [rawTicker, item] of Object.entries(data)) {
        const future = Array.isArray((item as any)?.future)
          ? (item as any).future
          : [];
        const last = future.at(-1);
        const ticker = rawTicker.trim().toUpperCase();
        const lastClosePrice = Number((item as any)?.last_close_price);
        const predictedPrice = Number(last?.predicted_close);
        const rawPEnsemble = Number((item as any)?.p_ensemble);
        if (
          ticker &&
          Number.isFinite(lastClosePrice) &&
          Number.isFinite(predictedPrice)
        ) {
          rows.push({
            ticker,
            lastClosePrice,
            predictedPrice,
            pEnsemble: Number.isFinite(rawPEnsemble) ? rawPEnsemble : null,
            chartPath: (item as any)?.chart_path ?? null,
            predictedOn: new Date((item as any)?.predicted_on ?? Date.now()),
          });
        }
      }
    }
    return rows;
  }

  async importFromJson(jsonPath = this.resolveJsonPath()) {
    const data = this.readPredictionFile(jsonPath);

    if (!data) {
      this.logger.error('❌ Không tìm thấy dữ liệu JSON để import');
      return {
        success: false,
        message: 'Không tìm thấy file dự đoán hoặc file rỗng.',
      };
    }

    const rows = this.normalizeRows(data);
    if (rows.length !== 50) {
      this.logger.error(`LSTM JSON must contain exactly 50 symbols; got ${rows.length}.`);
      return {
        success: false,
        message: 'JSON dự báo LSTM chưa đủ 50 mã.',
      };
    }

    // Xóa dữ liệu cũ (tránh trùng dữ liệu)
    await this.repo.clear();

    // Persist the snapshot in one transaction instead of paying one
    // transaction round-trip per symbol through the SSH tunnel.
    await this.repo.save(rows, { chunk: rows.length });

    this.logger.log('✅ Import dữ liệu dự đoán thành công');

    return {
      success: true,
      message: 'Import dự đoán thành công',
    };
  }

  /** Lưu từng prediction */
  async savePrediction(dto: {
    ticker: string;
    lastClosePrice: number;
    predictedPrice: number;
    pEnsemble?: number | null;
    chartPath?: string | null;
  }) {
    return await this.repo.save({
      ticker: dto.ticker,
      lastClosePrice: dto.lastClosePrice,
      predictedPrice: dto.predictedPrice,
      pEnsemble: dto.pEnsemble ?? null,
      chartPath: dto.chartPath ?? null,
      predictedOn: new Date(),
    });
  }

  /** Lấy dự đoán mới nhất theo mã */
  async getLatest(
    ticker: string,
  ): Promise<BaseResDataI<StockPredictionResI | null>> {
    const entity = await this.repo.findOne({
      where: { ticker },
      order: { predictedOn: 'DESC' },
    });

    if (!entity) {
      return {
        status: HttpStatusCode.OK,
        code: ResponseCode.SUCCESS,
        message: 'Không có dự đoán cho mã này',
        data: null,
      };
    }

    return {
      status: HttpStatusCode.OK,
      code: ResponseCode.SUCCESS,
      message: 'Lấy dự đoán mới nhất thành công',
      data: entity as unknown as StockPredictionResI,
    };
  }

  /** Phân trang */
  async findAll(query: Record<string, any>) {
    const page = Number(query.page) || 1;
    const limit = Number(query.limit) || 10;
    const search = String(query.search ?? '').trim().toLowerCase();
    const alias = 'stockPrediction';

    // Keep this query local to StockPrediction. BaseServices selects physical
    // database names, which causes mapped columns such as
    // pEnsemble -> p_ensemble to be returned as raw values instead of being
    // hydrated onto the entity property.
    const predictionQuery = this.repo
      .createQueryBuilder(alias)
      .select([
        `${alias}.id`,
        `${alias}.ticker`,
        `${alias}.lastClosePrice`,
        `${alias}.predictedPrice`,
        `${alias}.pEnsemble`,
        `${alias}.chartPath`,
        `${alias}.predictedOn`,
      ])
      .where(`${alias}.active = :active`, { active: true })
      .andWhere(`${alias}.deletedAt IS NULL`)
      .orderBy(`${alias}.modifiedAt`, 'DESC')
      .take(limit)
      .skip((page - 1) * limit);

    if (search) {
      predictionQuery.andWhere(`LOWER(${alias}.ticker) LIKE :search`, {
        search: `%${search}%`,
      });
    }

    const [data, total] = await predictionQuery.getManyAndCount();

    return {
      status: HttpStatusCode.OK,
      code: ResponseCode.SUCCESS,
      message: 'Lấy danh sách dự đoán cổ phiếu thành công',
      data,
      meta: {
        page,
        limit,
        total,
        totalPages: Math.ceil(total / limit),
      },
    };
  }
}
