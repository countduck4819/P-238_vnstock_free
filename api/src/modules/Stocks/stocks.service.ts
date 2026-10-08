import { Inject, Injectable, Logger, OnModuleInit } from '@nestjs/common';
import { Repository } from 'typeorm';
import { BaseServices } from '../Base/base.services';
import {
  StocksRepository,
  StocksServiceI,
  HttpStatusCode,
  ResponseCode,
} from 'src/shared';
import { StockEntity } from './stocks.entities';
import { IndustryEntity } from '../Industries/industries.entities';
import * as fs from 'fs';
import * as path from 'path';

@Injectable()
export class StockService
  extends BaseServices<StockEntity>
  implements StocksServiceI, OnModuleInit {
  private readonly logger = new Logger(StockService.name);

  private readonly jsonPath = path.resolve(
    process.cwd(),
    '../data/stocks_by_industries.json',
  );
  private readonly listingPath = path.resolve(
    process.cwd(),
    '../data/listing.json',
  );
  private readonly industriesForCodeCandidates = [
    path.resolve(process.cwd(), '../data/industries_for_code.json'),
    path.resolve(process.cwd(), 'data/industries_for_code.json'),
    path.resolve(process.cwd(), '../python_data/data/industries_for_code.json'),
  ];

  constructor(
    @Inject(StocksRepository)
    protected readonly stockRepository: Repository<StockEntity>,
  ) {
    super(stockRepository);
  }

  async findByIndustry(industryId: number) {
    return this.find({ industryId });
  }

  async getListingStock() {
    try {
      const stocks = await this.stockRepository.find({
        relations: ['industry'],
        order: { code: 'ASC' },
      });

      // Khử trùng lặp theo code, ưu tiên bản ghi có tên công ty đầy đủ
      const stockMap = new Map<
        string,
        {
          symbol: string;
          org_name: string;
          organ_name: string;
          industry_name: string;
        }
      >();

      for (const s of stocks) {
        if (!s.code) continue;
        const sym = s.code.toUpperCase().trim();
        const existing = stockMap.get(sym);
        const name = (s.name || '').trim();
        const indName = s.industry?.name || '';

        if (
          !existing ||
          (!existing.org_name && name) ||
          (existing.org_name === sym && name && name !== sym)
        ) {
          stockMap.set(sym, {
            symbol: sym,
            org_name: name || sym,
            organ_name: name || sym,
            industry_name: indName || existing?.industry_name || '',
          });
        }
      }

      // Nếu database có ít dữ liệu (< 500 mã), bổ sung từ file industries_for_code.json
      if (stockMap.size < 500) {
        for (const fp of this.industriesForCodeCandidates) {
          if (fs.existsSync(fp)) {
            try {
              const raw = JSON.parse(fs.readFileSync(fp, 'utf-8'));
              if (Array.isArray(raw)) {
                for (const item of raw) {
                  if (!item?.symbol) continue;
                  const sym = String(item.symbol).toUpperCase().trim();
                  const name = String(
                    item.organ_name || item.org_name || '',
                  ).trim();
                  const indName = String(
                    item.icb_name3 ||
                      item.icb_name2 ||
                      item.industry_name ||
                      '',
                  ).trim();
                  const existing = stockMap.get(sym);
                  if (
                    !existing ||
                    (!existing.org_name && name) ||
                    (existing.org_name === sym && name && name !== sym)
                  ) {
                    stockMap.set(sym, {
                      symbol: sym,
                      org_name: name || sym,
                      organ_name: name || sym,
                      industry_name: indName || existing?.industry_name || '',
                    });
                  }
                }
                break;
              }
            } catch (e: any) {
              this.logger.warn(
                `Lỗi đọc file fallback industries_for_code.json: ${e.message}`,
              );
            }
          }
        }
      }

      const data = Array.from(stockMap.values()).sort((a, b) =>
        a.symbol.localeCompare(b.symbol),
      );

      return {
        status: HttpStatusCode.OK,
        code: ResponseCode.SUCCESS,
        message: 'Lấy danh sách mã chứng khoán thành công',
        data,
      };
    } catch (err: any) {
      this.logger.error(`getListingStock error: ${err.message}`);
      return {
        status: HttpStatusCode.INTERNAL_ERROR,
        code: ResponseCode.ERROR,
        message: 'Không thể tải danh sách mã chứng khoán',
        data: [],
      };
    }
  }

  async getStockSymbols() {
    try {
      const stocks = await this.stockRepository.find({
        select: ['code'],
        order: { code: 'ASC' },
      });
      const set = new Set<string>();
      for (const s of stocks) {
        if (s.code) set.add(s.code.toUpperCase().trim());
      }

      // Nếu ít hơn 500 mã, bổ sung từ file fallback
      if (set.size < 500) {
        for (const fp of this.industriesForCodeCandidates) {
          if (fs.existsSync(fp)) {
            try {
              const raw = JSON.parse(fs.readFileSync(fp, 'utf-8'));
              if (Array.isArray(raw)) {
                for (const item of raw) {
                  if (item?.symbol) set.add(String(item.symbol).toUpperCase().trim());
                }
                break;
              }
            } catch {}
          }
        }
      }

      return {
        status: HttpStatusCode.OK,
        code: ResponseCode.SUCCESS,
        message: 'Lấy danh sách mã chứng khoán thành công',
        data: Array.from(set).sort(),
      };
    } catch (err: any) {
      this.logger.error(`getStockSymbols error: ${err.message}`);
      return {
        status: HttpStatusCode.INTERNAL_ERROR,
        code: ResponseCode.ERROR,
        message: 'Không thể tải danh sách mã chứng khoán',
        data: [],
      };
    }
  }

  async getCandleData(symbol: string) {
    const sym = symbol.toUpperCase().trim();
    try {
      // 1. Try python upstream if available
      const pythonUrl = (
        process.env.PYTHON_API_URL || 'http://python_data:6060/api'
      ).replace(/\/+$/, '');
      const res = await fetch(`${pythonUrl}/stock/${sym}`, {
        signal: AbortSignal.timeout(15000),
      });
      if (res.ok) {
        const raw = await res.json();
        if (Array.isArray(raw) && raw.length > 0) {
          return raw;
        }
      }
    } catch (err: any) {
      this.logger.warn(`getCandleData python error for ${sym}: ${err.message}`);
    }

    // 2. Read from disk data/stocks/SYMBOL.json
    try {
      const candidates = [
        path.resolve(process.cwd(), `data/stocks/${sym}.json`),
        path.resolve(process.cwd(), `../data/stocks/${sym}.json`),
        path.resolve(process.cwd(), `../python_data/data/stocks/${sym}.json`),
      ];
      for (const p of candidates) {
        if (fs.existsSync(p)) {
          const raw = JSON.parse(fs.readFileSync(p, 'utf-8'));
          if (Array.isArray(raw) && raw.length > 0) {
            return raw;
          }
        }
      }
    } catch {}

    return [];
  }

  async getOverview() {
    try {
      const pythonUrl = (
        process.env.PYTHON_API_URL || 'http://python_data:6060/api'
      ).replace(/\/+$/, '');
      const res = await fetch(`${pythonUrl}/stocks/overview`, {
        signal: AbortSignal.timeout(5000),
      });
      if (res.ok) {
        const data = await res.json();
        return {
          status: HttpStatusCode.OK,
          code: ResponseCode.SUCCESS,
          message: 'Lấy tổng quan thị trường thành công',
          data,
        };
      }
    } catch (err: any) {
      this.logger.warn(`getOverview proxy error: ${err.message}`);
    }
    return {
      status: HttpStatusCode.OK,
      code: ResponseCode.SUCCESS,
      message: 'Dữ liệu tổng quan mặc định',
      data: {},
    };
  }


  async onModuleInit() {
    await this.syncFromJson();
  }

  private readJson(filePath: string): any {
    try {
      if (!fs.existsSync(filePath)) return null;
      const content = fs.readFileSync(filePath, 'utf-8');
      return JSON.parse(content);
    } catch (err: any) {
      this.logger.error(`Lỗi đọc file ${filePath}:`, err.message);
      return null;
    }
  }

  private async syncFromJson() {
    try {
      const industriesRepo =
        this.stockRepository.manager.getRepository(IndustryEntity);

      // 1. Dọn dẹp các mã bị trùng lặp trong DB nếu có
      const allExisting = await this.stockRepository.find();
      const codeToStocksMap = new Map<string, StockEntity[]>();
      for (const s of allExisting) {
        const sym = s.code.toUpperCase().trim();
        if (!codeToStocksMap.has(sym)) {
          codeToStocksMap.set(sym, []);
        }
        codeToStocksMap.get(sym)!.push(s);
      }

      const duplicateIdsToDelete: number[] = [];
      for (const [_, stockList] of codeToStocksMap.entries()) {
        if (stockList.length > 1) {
          // Giữ lại bản ghi có tên đầy đủ nhất (không rỗng và không trùng symbol)
          stockList.sort((a, b) => {
            const aGood = a.name && a.name !== a.code ? 1 : 0;
            const bGood = b.name && b.name !== b.code ? 1 : 0;
            if (bGood !== aGood) return bGood - aGood;
            return a.id - b.id;
          });
          // Bản ghi đầu tiên giữ lại, các bản ghi sau đưa vào danh sách xóa
          for (let i = 1; i < stockList.length; i++) {
            duplicateIdsToDelete.push(stockList[i].id);
          }
        }
      }

      if (duplicateIdsToDelete.length > 0) {
        // Xóa các bản ghi trùng lặp
        for (let i = 0; i < duplicateIdsToDelete.length; i += 100) {
          const chunk = duplicateIdsToDelete.slice(i, i + 100);
          await this.stockRepository.delete(chunk);
        }
        this.logger.log(`Đã dọn dẹp ${duplicateIdsToDelete.length} bản ghi cổ phiếu bị trùng lặp trong DB`);
      }

      // 2. Đồng bộ từ industries_for_code.json nếu có
      let industriesForCodePath: string | null = null;
      for (const p of this.industriesForCodeCandidates) {
        if (fs.existsSync(p)) {
          industriesForCodePath = p;
          break;
        }
      }

      if (industriesForCodePath) {
        const listData = this.readJson(industriesForCodePath);
        if (Array.isArray(listData) && listData.length > 0) {
          const existingIndustries = await industriesRepo.find();
          const industryNameMap = new Map<string, number>(
            existingIndustries.map((i) => [i.name.trim(), i.id]),
          );

          // Thu thập các ngành chưa có
          const newIndustryNames = new Set<string>();
          for (const item of listData) {
            const indName = String(item.icb_name3 || item.icb_name2 || '').trim();
            if (indName && !industryNameMap.has(indName)) {
              newIndustryNames.add(indName);
            }
          }

          if (newIndustryNames.size > 0) {
            const insertedInd = await industriesRepo.save(
              Array.from(newIndustryNames).map((name) => ({ name })),
            );
            for (const ind of insertedInd) {
              industryNameMap.set(ind.name.trim(), ind.id);
            }
          }

          const defaultIndustryId =
            industryNameMap.values().next().value || 1;

          const currentStocks = await this.stockRepository.find();
          const currentMap = new Map<string, StockEntity>(
            currentStocks.map((s) => [s.code.toUpperCase().trim(), s]),
          );

          const toInsert: Partial<StockEntity>[] = [];
          const toUpdate: { id: number; name: string; industryId: number }[] = [];
          const seenInBatch = new Set<string>();

          for (const item of listData) {
            if (!item?.symbol) continue;
            const sym = String(item.symbol).toUpperCase().trim();
            if (seenInBatch.has(sym)) continue;
            seenInBatch.add(sym);

            const companyName = String(item.organ_name || item.org_name || sym).trim();
            const indName = String(item.icb_name3 || item.icb_name2 || '').trim();
            const industryId = industryNameMap.get(indName) || defaultIndustryId;

            const existingStock = currentMap.get(sym);
            if (!existingStock) {
              toInsert.push({ code: sym, name: companyName, industryId });
            } else {
              const needUpdate =
                (!existingStock.name || existingStock.name === sym) && companyName !== sym;
              if (needUpdate) {
                toUpdate.push({
                  id: existingStock.id,
                  name: companyName,
                  industryId: existingStock.industryId || industryId,
                });
              }
            }
          }

          if (toInsert.length > 0) {
            for (let i = 0; i < toInsert.length; i += 200) {
              const chunk = toInsert.slice(i, i + 200);
              await this.stockRepository.insert(chunk);
            }
            this.logger.log(`Đã thêm ${toInsert.length} mã cổ phiếu mới từ industries_for_code`);
          }

          if (toUpdate.length > 0) {
            for (const stock of toUpdate) {
              await this.stockRepository.update(stock.id, {
                name: stock.name,
              });
            }
            this.logger.log(`Đã cập nhật tên cho ${toUpdate.length} mã cổ phiếu`);
          }

          return;
        }
      }

      // 3. Fallback đồng bộ từ stocks_by_industries.json và listing.json nếu có
      const data = this.readJson(this.jsonPath);
      const listing = this.readJson(this.listingPath);

      if (!data || Object.keys(data).length === 0) {
        return;
      }

      const nameMap = new Map<string, string>(
        (Array.isArray(listing) ? listing : []).map((i: any) => [
          String(i.symbol).toUpperCase().trim(),
          String(i.org_name || i.organ_name || '').trim(),
        ]),
      );

      const industries = await industriesRepo.find();
      const industryMap = new Map<string, number>(
        industries.map((i) => [i.name.trim(), i.id]),
      );

      const existing = await this.stockRepository.find();
      const existingMap = new Map<string, StockEntity>(
        existing.map((s) => [s.code.toUpperCase().trim(), s]),
      );

      const toInsert: Partial<StockEntity>[] = [];
      const toUpdate: { id: number; name: string; industryId: number }[] = [];
      const seenCodes = new Set<string>();

      for (const [industryNameRaw, symbols] of Object.entries(data)) {
        const industryName = industryNameRaw.trim();
        const industryId = industryMap.get(industryName);

        if (!industryId) {
          continue;
        }

        for (const rawCode of symbols as string[]) {
          const code = String(rawCode).toUpperCase().trim();
          if (seenCodes.has(code)) continue;
          seenCodes.add(code);

          const companyName = nameMap.get(code) || code;
          const existingStock = existingMap.get(code);

          if (!existingStock) {
            toInsert.push({ code, name: companyName, industryId });
          } else {
            const needUpdate =
              existingStock.industryId !== industryId ||
              !existingStock.name ||
              existingStock.name === code;

            if (needUpdate) {
              toUpdate.push({
                id: existingStock.id,
                name: companyName,
                industryId,
              });
            }
          }
        }
      }

      if (toInsert.length > 0) {
        await this.stockRepository.insert(toInsert);
        this.logger.log(`Đã thêm ${toInsert.length} cổ phiếu mới`);
      }

      if (toUpdate.length > 0) {
        for (const stock of toUpdate) {
          await this.stockRepository.update(stock.id, {
            name: stock.name,
            industryId: stock.industryId,
          });
        }
        this.logger.log(`Đã cập nhật ${toUpdate.length} cổ phiếu (tên/ngành)`);
      }
    } catch (err: any) {
      this.logger.error(`Lỗi syncFromJson: ${err.message}`);
    }
  }

  async paginate(condition: Record<string, any> = {}, page = 1, limit = 10) {
    try {
      const qb = this.stockRepository
        .createQueryBuilder('stock')
        .leftJoinAndSelect('stock.industry', 'industry')
        .select([
          'stock.id',
          'stock.code',
          'stock.name',
          'industry.id',
          'industry.name',
        ])
        .where('stock.active = true')
        .andWhere('stock.deletedAt IS NULL');

      // 🎯 Bỏ qua page, limit
      delete condition.page;
      delete condition.limit;

      // 🔍 Nếu có search → tìm theo code hoặc name (ILIKE)
      if (condition.search) {
        const s = `%${String(condition.search).trim()}%`;
        qb.andWhere('(stock.code ILIKE :search OR stock.name ILIKE :search)', {
          search: s,
        });
      }

      // Các điều kiện khác nếu có (industryId, ...)
      for (const [key, value] of Object.entries(condition)) {
        if (!value || key === 'search') continue;
        qb.andWhere(`stock.${key} = :${key}`, { [key]: value });
      }

      qb.orderBy('stock.id', 'ASC');

      const [data, total] = await qb
        .take(limit)
        .skip((page - 1) * limit)
        .getManyAndCount();

      return {
        status: 200,
        code: 1,
        message: 'Lấy danh sách cổ phiếu thành công',
        data,
        meta: {
          page,
          limit,
          total,
          totalPages: Math.ceil(total / limit),
        },
      };
    } catch (error) {
      this.logger.error(`paginate() lỗi: ${error.message}`);
      return {
        status: 200,
        code: 1,
        message: 'Không tìm thấy dữ liệu phù hợp',
        data: [],
        meta: { page, limit, total: 0, totalPages: 0 },
      };
    }
  }
}
