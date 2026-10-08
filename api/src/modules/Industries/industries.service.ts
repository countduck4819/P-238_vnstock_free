import { IndustryEntity } from './industries.entities';
import {
  IndustryRepository,
  IndustryServiceI,
  HttpStatusCode,
  ResponseCode,
  BaseResDataI,
} from 'src/shared';
import { Inject, Injectable, Logger, OnModuleInit } from '@nestjs/common';
import { BaseServices } from '../Base/base.services';
import { Repository } from 'typeorm';
import * as fs from 'fs';
import * as path from 'path';

@Injectable()
export class IndustryService
  extends BaseServices<IndustryEntity>
  implements IndustryServiceI, OnModuleInit
{
  private readonly logger = new Logger(IndustryService.name);
  private readonly jsonPath = path.resolve(
    process.cwd(),
    '../data/industries.json',
  );

  constructor(
    @Inject(IndustryRepository)
    protected readonly industryRepository: Repository<IndustryEntity>,
  ) {
    super(industryRepository);
  }

  async getIndustries() {
    try {
      const industries = await this.industryRepository.find({
        where: { active: true },
        order: { id: 'ASC' },
      });
      const data = industries.map((i) => i.name);
      return {
        status: HttpStatusCode.OK,
        code: ResponseCode.SUCCESS,
        message: 'Lấy danh sách ngành thành công',
        data,
      };
    } catch (err: any) {
      this.logger.error(`getIndustries error: ${err.message}`);
      return {
        status: HttpStatusCode.INTERNAL_ERROR,
        code: ResponseCode.ERROR,
        message: 'Không thể lấy danh sách ngành',
        data: [],
      };
    }
  }

  async getStocksByIndustries() {
    try {
      const industries = await this.industryRepository.find({
        where: { active: true },
        relations: ['stocks'],
        order: { id: 'ASC' },
      });
      const result: Record<string, string[]> = {};
      for (const ind of industries) {
        result[ind.name] = (ind.stocks || [])
          .filter((s) => s.active && !s.deletedAt)
          .map((s) => s.code);
      }
      return {
        status: HttpStatusCode.OK,
        code: ResponseCode.SUCCESS,
        message: 'Lấy danh sách cổ phiếu theo ngành thành công',
        data: result,
      };
    } catch (err: any) {
      this.logger.error(`getStocksByIndustries error: ${err.message}`);
      return {
        status: HttpStatusCode.INTERNAL_ERROR,
        code: ResponseCode.ERROR,
        message: 'Không thể lấy danh sách cổ phiếu theo ngành',
        data: {},
      };
    }
  }

  /** Ghi đè lại find() → paginate riêng + đúng kiểu trả về */
  async find(query: Record<string, any>): Promise<any> {
    const page = Number(query.page) || 1;
    const limit = Number(query.limit) || 10;
    const { page: _p, limit: _l, search, ...condition } = query;
    const searchFilters = search ? { name: search } : undefined;
    const result = await this.paginateWithModifiedAt(
      condition,
      page,
      limit,
      searchFilters,
    );

    const data = Array.isArray(result.data) ? result.data : [];
    data.sort((a: any, b: any) => a.id - b.id);

    const formatted = data.map((item: any) => ({
      ...item,
      modifiedAt:
        item.modifiedAt || item.createdAt
          ? new Date(item.modifiedAt || item.createdAt).toISOString()
          : null,
    }));

    return {
      status: HttpStatusCode.OK,
      code: ResponseCode.SUCCESS,
      message: 'Lấy danh sách ngành thành công',
      data: formatted,
      meta: result.meta,
    } as any; // ép kiểu
  }

  /** Phân trang riêng có modifiedAt */
  private async paginateWithModifiedAt(
    condition: Record<string, any> = {},
    page = 1,
    limit = 10,
    searchFilters?: Record<string, any>,
  ) {
    const alias = this.industryRepository.metadata.tableName;
    const query = this.industryRepository
      .createQueryBuilder(alias)
      .where(`${alias}.active = true`)
      .andWhere(`${alias}.deletedAt IS NULL`);

    for (const [key, value] of Object.entries(condition)) {
      if (value !== undefined && value !== null && value !== '') {
        query.andWhere(`${alias}.${key} = :${key}`, { [key]: value });
      }
    }

    if (searchFilters && Object.keys(searchFilters).length > 0) {
      const exprs: string[] = [];
      const params: Record<string, any> = {};
      for (const [key, value] of Object.entries(searchFilters)) {
        if (value) {
          const paramKey = `search_${key}`;
          exprs.push(`LOWER(${alias}.${key}) LIKE :${paramKey}`);
          params[paramKey] = `%${(value as any).toLowerCase()}%`;
        }
      }
      if (exprs.length > 0) query.andWhere(`(${exprs.join(' OR ')})`, params);
    }

    query.select([
      `${alias}.id`,
      `${alias}.name`,
      `${alias}.modifiedAt`,
      `${alias}.createdAt`,
    ]);

    query.orderBy(`${alias}.modifiedAt`, 'DESC');

    const [data, total] = await query
      .take(limit)
      .skip((page - 1) * limit)
      .getManyAndCount();

    return {
      data,
      meta: {
        page,
        limit,
        total,
        totalPages: Math.ceil(total / limit),
      },
    };
  }

  async onModuleInit() {
    if (fs.existsSync(this.jsonPath)) {
      await this.syncFromJson();
    }
  }

  private readJson(): string[] {
    try {
      if (!fs.existsSync(this.jsonPath)) return [];
      const content = fs.readFileSync(this.jsonPath, 'utf-8');
      const parsed = JSON.parse(content);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }

  private async syncFromJson() {
    const names = this.readJson();
    if (!names.length) return;

    const existing = await this.industryRepository.find();
    const existingNames = new Set(existing.map((i) => i.name));

    const toAdd = names.filter((n) => !existingNames.has(n));
    if (toAdd.length > 0) {
      await this.industryRepository.insert(toAdd.map((n) => ({ name: n })));
      this.logger.log(`Đã thêm ${toAdd.length} ngành mới`);
    }
  }
}
