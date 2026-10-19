import { Inject, Injectable } from '@nestjs/common';
import * as fs from 'fs';
import * as path from 'path';
import {
  HttpStatusCode,
  NewsRepository,
  NewsServiceI,
  ResponseCode,
} from 'src/shared';
import { BaseServices } from '../Base/base.services';
import { NewsEntity } from './news.entities';
import { Repository } from 'typeorm';
import { pythonApiUrl } from 'src/shared/common/python-api';

@Injectable()
export class NewsService
  extends BaseServices<NewsEntity>
  implements NewsServiceI
{
  constructor(
    @Inject(NewsRepository)
    protected readonly newsRepository: Repository<NewsEntity>,
  ) {
    super(newsRepository as unknown as Repository<NewsEntity>);
  }

  // =========================================================
  // Đọc dữ liệu từ file JSON Python export
  // =========================================================

  async getFromJson(symbol: string) {
    try {
      const normalizedSymbol = symbol.toUpperCase().trim();
      const filePath = path.join(
        process.cwd(),
        '../data/news',
        `${normalizedSymbol}_news.json`,
      );

      // python_data chỉ trả metadata và ghi danh sách tin vào data/news dùng
      // chung, nên khi chưa có file thì nhờ nó tạo cache rồi đọc lại file.
      if (!fs.existsSync(filePath)) {
        await this.warmPythonNewsCache(normalizedSymbol);
      }

      if (fs.existsSync(filePath)) {
        const raw = fs.readFileSync(filePath, 'utf8');
        const data = JSON.parse(raw);
        return {
          status: HttpStatusCode.OK,
          code: ResponseCode.SUCCESS,
          message: 'Đọc JSON thành công',
          data,
        };
      }

      return {
        status: HttpStatusCode.NOT_FOUND,
        code: ResponseCode.ERROR,
        message: `Không tìm thấy tin tức cho ${normalizedSymbol}`,
        data: null,
      };
    } catch (e) {
      return {
        status: HttpStatusCode.INTERNAL_ERROR,
        code: ResponseCode.ERROR,
        message: `Lỗi lấy tin tức: ${(e as Error).message}`,
        data: null,
      };
    }
  }

  private async warmPythonNewsCache(symbol: string): Promise<void> {
    try {
      await fetch(pythonApiUrl(`/news/${symbol}`));
    } catch {
      // python_data chưa sẵn sàng: caller trả NOT_FOUND.
    }
  }

  // =========================================================
  // Đồng bộ toàn bộ news JSON vào DB
  //
  // Lưu ý:
  // - page / limit giữ lại để không phá API/interface cũ.
  // - Không dùng page/limit ở đây nữa.
  // - Pagination 10 bài/lần xử lý ở paginateNews().
  // =========================================================

  async importBatch(
    symbol: string,
    _page = 1,
    _limit = 10,
  ) {
    const normalizedSymbol = symbol.toUpperCase().trim();

    const jsonRes = await this.getFromJson(
      normalizedSymbol,
    );

    if (
      !jsonRes.data ||
      !Array.isArray(jsonRes.data.data)
    ) {
      return jsonRes;
    }

    const allNews = jsonRes.data.data;

    if (allNews.length === 0) {
      return {
        status: HttpStatusCode.OK,
        code: ResponseCode.SUCCESS,
        message: `Không có news để đồng bộ cho ${normalizedSymbol}`,
        data: {
          total: 0,
          synced: 0,
        },
      };
    }

    const now = new Date();

    const insertData = allNews.map(
      (item: any) => ({
        news_id:
          item.news_id || item.slug,

        news_title:
          item.news_title || '',

        news_sub_title:
          item.news_sub_title || '',

        news_short_content:
          item.news_short_content || '',

        news_full_content:
          item.news_full_content || '',

        news_image_url:
          item.news_image_url || '',

        news_source_link:
          item.news_source_link || '',

        public_date:
          item.public_date || null,

        slug:
          item.slug || item.news_id,

        symbol:
          normalizedSymbol,

        active:
          true,

        createdAt:
          now,

        modifiedAt:
          now,
      }),
    );

    // =====================================================
    // UPSERT
    //
    // news_id chưa có:
    // => INSERT
    //
    // news_id đã tồn tại:
    // => UPDATE lại content, PDF, image...
    // =====================================================

    await this.newsRepository
      .createQueryBuilder()
      .insert()
      .into(NewsEntity)
      .values(insertData)
      .orUpdate(
        [
          'news_title',
          'news_sub_title',
          'news_short_content',
          'news_full_content',
          'news_image_url',
          'news_source_link',
          'public_date',
          'slug',
          'symbol',
          'active',
          'modifiedAt',
        ],
        [
          'news_id',
        ],
      )
      .execute();

    return {
      status: HttpStatusCode.OK,
      code: ResponseCode.SUCCESS,
      message: `Đã đồng bộ ${allNews.length} bài cho ${normalizedSymbol}`,
      data: {
        total: allNews.length,
        synced: allNews.length,
      },
    };
  }

  // =========================================================
  // Phân trang news từ DB
  //
  // Frontend:
  //
  // page=1&limit=10
  // => 10 bài mới nhất
  //
  // scroll:
  // page=2&limit=10
  // => 10 bài tiếp
  // =========================================================

  async paginateNews(
    page = 1,
    limit = 10,
    symbol?: string,
  ) {
    const safePage = Math.max(
      Number(page) || 1,
      1,
    );

    const safeLimit = Math.max(
      Number(limit) || 10,
      1,
    );

    const qb = this.newsRepository
      .createQueryBuilder('news')
      .where('news.active = true')
      .orderBy(
        'news.public_date',
        'DESC',
      )
      .take(safeLimit)
      .skip(
        (safePage - 1) * safeLimit,
      );

    if (
      symbol &&
      symbol.toUpperCase() !== 'VNINDEX'
    ) {
      qb.andWhere(
        'news.symbol = :symbol',
        {
          symbol:
            symbol
              .toUpperCase()
              .trim(),
        },
      );
    }

    const [data, total] =
      await qb.getManyAndCount();

    return {
      status: HttpStatusCode.OK,
      code: ResponseCode.SUCCESS,
      message: 'Lấy tin tức thành công',
      data,
      meta: {
        page: safePage,
        limit: safeLimit,
        total,
        hasMore:
          safePage * safeLimit < total,
      },
    };
  }

  // =========================================================
  // Chi tiết news theo slug
  // =========================================================

  async findBySlug(slug: string) {
    const news =
      await this.newsRepository.findOne({
        where: {
          slug,
        },
      });

    if (!news) {
      return {
        status: HttpStatusCode.NOT_FOUND,
        code: ResponseCode.ERROR,
        message:
          `Không tìm thấy bài viết với slug ${slug}`,
        data: null,
      };
    }

    return {
      status: HttpStatusCode.OK,
      code: ResponseCode.SUCCESS,
      message:
        `Chi tiết bài viết: ${news.news_title}`,
      data: news,
    };
  }

  // =========================================================
  // Search + pagination
  // =========================================================

  async searchNews(
    page = 1,
    limit = 10,
    keyword?: string,
  ) {
    const safePage = Math.max(
      Number(page) || 1,
      1,
    );

    const safeLimit = Math.max(
      Number(limit) || 10,
      1,
    );

    const qb = this.newsRepository
      .createQueryBuilder('news')
      .where('news.active = true');

    if (keyword?.trim()) {
      qb.andWhere(
        `(
          LOWER(news.news_title) LIKE LOWER(:kw)
          OR LOWER(news.slug) LIKE LOWER(:kw)
        )`,
        {
          kw: `%${keyword.trim()}%`,
        },
      );
    }

    qb
      .orderBy(
        'news.public_date',
        'DESC',
      )
      .take(safeLimit)
      .skip(
        (safePage - 1) * safeLimit,
      );

    const [data, total] =
      await qb.getManyAndCount();

    return {
      status: HttpStatusCode.OK,
      code: ResponseCode.SUCCESS,
      message:
        'Tìm kiếm tin tức thành công',
      data,
      meta: {
        page: safePage,
        limit: safeLimit,
        total,
        hasMore:
          safePage * safeLimit < total,
      },
    };
  }
}