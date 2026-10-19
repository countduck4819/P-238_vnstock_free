import {
  Inject,
  Injectable,
  Logger,
  OnApplicationBootstrap,
} from '@nestjs/common';
import { Cron, CronExpression } from '@nestjs/schedule';
import { DataSource } from 'typeorm';
import { DATA_SOURCE, NewsServiceToken } from 'src/shared';
import { NewsService } from './news.service';

// Mã lấy tin mặc định khi không cấu hình NEWS_SYNC_SYMBOLS: rổ VN30.
const DEFAULT_SYMBOLS = (
  'ACB,BCM,BID,BVH,CTG,FPT,GAS,GVR,HDB,HPG,LPB,MBB,MSN,MWG,PLX,' +
  'SAB,SHB,SSB,SSI,STB,TCB,TPB,VCB,VHM,VIB,VIC,VJC,VNM,VPB,VRE'
).split(',');

/**
 * Tự lấy tin tức của nhiều mã về DB theo lịch, để bảng tin ở trang chủ có
 * sẵn dữ liệu mà không cần ai mở từng trang mã cổ phiếu.
 *
 * Mỗi mã đi qua đúng luồng cũ: python_data gọi vnstock và ghi cache JSON,
 * NestJS đọc JSON rồi upsert vào bảng news (trùng news_id thì cập nhật).
 * Các mã chạy tuần tự vì vnstock bản free giới hạn số request mỗi phút.
 */
@Injectable()
export class NewsSyncService implements OnApplicationBootstrap {
  private readonly logger = new Logger(NewsSyncService.name);
  private running = false;

  constructor(
    @Inject(NewsServiceToken)
    private readonly newsService: NewsService,
    @Inject(DATA_SOURCE)
    private readonly dataSource: DataSource,
  ) {}

  private get enabled() {
    return !['0', 'false', 'off', 'no'].includes(
      String(process.env.NEWS_SYNC_ENABLED ?? '1')
        .trim()
        .toLowerCase(),
    );
  }

  onApplicationBootstrap() {
    if (!this.enabled) return;
    // Chờ python_data khởi động xong rồi mới lấy lượt đầu.
    setTimeout(() => void this.syncMarketNews(), 30_000);
  }

  @Cron(CronExpression.EVERY_30_MINUTES)
  handleCron() {
    if (this.enabled) return this.syncMarketNews();
  }

  async syncMarketNews() {
    if (this.running) return;
    this.running = true;

    try {
      const symbols = await this.symbols();
      let synced = 0;

      for (const symbol of symbols) {
        try {
          const res = await this.newsService.importBatch(symbol);
          const count = (res.data as { synced?: number } | null)?.synced;
          if (count) synced += count;
        } catch (e) {
          this.logger.warn(`Lấy tin ${symbol} lỗi: ${(e as Error).message}`);
        }
      }

      this.logger.log(`Đồng bộ tin tức ${symbols.length} mã, ${synced} bài`);
    } finally {
      this.running = false;
    }
  }

  /** Mã trong NEWS_SYNC_SYMBOLS (hoặc VN30) cộng các mã đang được khuyến nghị. */
  private async symbols(): Promise<string[]> {
    const configured = (process.env.NEWS_SYNC_SYMBOLS || '')
      .split(',')
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean);

    let recommended: string[] = [];
    try {
      const rows: { code: string }[] = await this.dataSource.query(
        `SELECT DISTINCT s.code FROM stock_recommendations r
         JOIN stocks s ON s.id = r."stockId"
         WHERE r."deletedAt" IS NULL`,
      );
      recommended = rows.map((r) => r.code.toUpperCase());
    } catch {
      // Bảng chưa có dữ liệu/chưa tạo: chỉ dùng danh sách cấu hình.
    }

    return [
      ...new Set([
        ...(configured.length ? configured : DEFAULT_SYMBOLS),
        ...recommended,
      ]),
    ];
  }
}
