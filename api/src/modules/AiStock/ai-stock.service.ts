import {
  Inject,
  Injectable,
  Logger,
  ServiceUnavailableException,
} from '@nestjs/common';
import { HttpService } from '@nestjs/axios';
import { firstValueFrom } from 'rxjs';
import Groq from 'groq-sdk';
import {
  AiStockAskReqI,
  AiStockAskResI,
  AiStockRepository,
  AiStockServiceI,
  BaseResDataI,
  HttpStatusCode,
  ResponseCode,
  StocksRepository,
} from 'src/shared';
import { Repository } from 'typeorm';
import { BaseServices } from 'src/modules/Base/base.services';
import { AiStockHistoryEntity } from './entities/ai-stock-history.entity';
import { StockEntity } from '../Stocks/stocks.entities';
import { pythonApiUrl } from 'src/shared/common/python-api';

@Injectable()
export class AiStockService
  extends BaseServices<AiStockHistoryEntity>
  implements AiStockServiceI
{
  private stockCodes: string[] = [];
  private readonly logger = new Logger(AiStockService.name);

  private readonly groq: Groq | null;

  private async loadStockCodes() {
    const rows = await this.stockRepository.find({
      select: ['code'],
      where: { active: true },
    });

    this.stockCodes = rows.map((r) => r.code.toUpperCase());
    this.logger.log(`Loaded ${this.stockCodes.length} stock codes.`);
  }
  constructor(
    @Inject(AiStockRepository)
    protected readonly aiStockRepository: Repository<AiStockHistoryEntity>,
    private readonly http: HttpService,
    @Inject(StocksRepository)
    protected readonly stockRepository: Repository<StockEntity>,
  ) {
    super(aiStockRepository);

    this.groq = process.env.GROQ_API_KEY
      ? new Groq({ apiKey: process.env.GROQ_API_KEY })
      : null;
    if (!this.groq) {
      this.logger.warn(
        'GROQ_API_KEY is absent; AI chat is unavailable but the API remains online.',
      );
    }

    this.loadStockCodes();
  }

  private requireGroq(): Groq {
    if (!this.groq) {
      throw new ServiceUnavailableException(
        'AI chat is not configured for this deployment.',
      );
    }
    return this.groq;
  }

  private async askFinSightBackend(
    body: AiStockAskReqI,
  ): Promise<BaseResDataI<AiStockAskResI> | null> {
    const configuredUrl = process.env.FINSIGHT_API_URL?.trim();
    if (!configuredUrl) return null;

    const baseUrl = configuredUrl.replace(/\/$/, '');
    const parsedTimeout = Number(process.env.FINSIGHT_API_TIMEOUT_MS ?? 120000);
    const timeout = Number.isFinite(parsedTimeout)
      ? Math.min(Math.max(parsedTimeout, 1000), 120000)
      : 120000;

    const recentHistories = body.userId
      ? await this.aiStockRepository.find({
          where: { userId: body.userId },
          order: { createdAt: 'DESC' },
          take: 6,
        })
      : [];
    const history = recentHistories.reverse().flatMap((item) => [
      { role: 'user', content: item.question.slice(0, 4000) },
      ...(item.answer
        ? [{ role: 'assistant', content: item.answer.slice(0, 4000) }]
        : []),
    ]);

    try {
      const response = await firstValueFrom(
        this.http.post(
          `${baseUrl}/api/v1/finsight/query`,
          {
            userId: body.userId,
            question: body.question,
            history,
          },
          { timeout },
        ),
      );
      const result = response.data?.data;
      if (typeof result?.answer !== 'string' || !result.answer.trim()) {
        throw new Error('FinSight returned an invalid response contract.');
      }

      const symbol = typeof result.symbol === 'string' ? result.symbol : null;
      await this.aiStockRepository.save({
        userId: body.userId,
        question: body.question,
        symbol,
        answer: result.answer,
      });

      return {
        status: HttpStatusCode.OK,
        code: ResponseCode.SUCCESS,
        message: 'Trợ lý ảo FinSight trả lời thành công',
        data: { symbol, answer: result.answer },
      };
    } catch (error) {
      const httpError = error as {
        response?: { status?: number; data?: { message?: unknown } };
      };
      if (httpError.response?.status === 429) {
        const upstreamMessage = httpError.response.data?.message;
        const answer =
          typeof upstreamMessage === 'string' && upstreamMessage.trim()
            ? upstreamMessage
            : 'Bạn đang gửi câu hỏi quá nhanh. Vui lòng thử lại sau ít phút.';
        return {
          status: HttpStatusCode.OK,
          code: ResponseCode.SUCCESS,
          message: 'FinSight đã giới hạn tần suất yêu cầu',
          data: { symbol: null, answer },
        };
      }
      const reason = error instanceof Error ? error.message : 'unknown error';
      this.logger.warn(
        `FinSight backend unavailable; using legacy fallback: ${reason}`,
      );
      return null;
    }
  }

  private detectSymbol(question: string): string | null {
    if (!question) return null;

    const words = question
      .toUpperCase()
      .replace(/[^A-Z0-9\s]/g, ' ')
      .split(/\s+/)
      .filter((w) => w.length >= 2 && w.length <= 5);

    for (const w of words) {
      if (this.stockCodes.includes(w)) {
        return w;
      }
    }

    return null;
  }

  private async fetchPrice(symbol: string) {
    try {
      const res = await firstValueFrom(
        this.http.get(pythonApiUrl(`/stock/${symbol}`)),
      );
      return res.data;
    } catch {
      return null;
    }
  }

  /** Python API: finance */
  private async fetchFinance(symbol: string) {
    try {
      const res = await firstValueFrom(
        this.http.get(pythonApiUrl(`/finance/${symbol}`)),
      );
      return res.data;
    } catch {
      return null;
    }
  }

  /** Nest API: news */
  private async fetchNews(symbol: string) {
    try {
      const res = await firstValueFrom(
        this.http.get(pythonApiUrl(`/news/${symbol}`), {
          params: { symbol, limit: 1, page: 1 },
        }),
      );

      return res.data?.data || [];
    } catch {
      return [];
    }
  }

  /** Summarize news */
  private async buildNewsSnippet(latest: any | null) {
    if (!latest) return null;

    const title = latest.news_title || '';
    const slug = latest.slug || '';
    const link = slug ? `${process.env.HOST_WEB}/tin-tuc/${slug}` : '';

    if (latest.news_short_content) {
      return {
        title,
        summary: latest.news_short_content,
        link,
      };
    }

    if (latest.news_full_content) {
      const result = await this.requireGroq().chat.completions.create({
        model: 'openai/gpt-oss-20b',
        messages: [
          {
            role: 'user',
            content: `Tóm tắt đoạn sau thành 1–2 câu, bỏ hết HTML:\n${latest.news_full_content}`,
          },
        ],
        temperature: 0.25,
      });

      return {
        title,
        summary: result.choices[0].message.content,
        link,
      };
    }

    return { title, summary: title, link };
  }

  //   async askStockAi(
  //     body: AiStockAskReqI,
  //   ): Promise<BaseResDataI<AiStockAskResI>> {
  //     const { userId, question } = body;

  //     const symbol = this.detectSymbol(question);

  //     /** CASE B — CÓ SYMBOL */
  //     // Nếu không có symbol → trả về data rỗng để không bị lỗi
  //     const [priceData, financeData, newsList] = symbol
  //       ? await Promise.all([
  //           this.fetchPrice(symbol),
  //           this.fetchFinance(symbol),
  //           this.fetchNews(symbol),
  //         ])
  //       : [null, null, []];

  //     const latestNews = newsList[0] || null;

  //     const newsSnippet = latestNews
  //       ? await this.buildNewsSnippet(latestNews)
  //       : null;

  //     const lastCandle = Array.isArray(priceData)
  //       ? priceData[priceData.length - 1]
  //       : null;

  //     const newsText = newsSnippet
  //       ? `
  // Tiêu đề: ${newsSnippet.title}
  // Tóm tắt: ${newsSnippet.summary}
  // Link: ${newsSnippet.link}
  //   `.trim()
  //       : 'Không có tin tức.';

  //     /** Build AI context */
  //     const context = `
  // DỮ LIỆU CỔ PHIẾU: ${symbol || 'Không tìm thấy mã'}

  // [GIÁ GẦN NHẤT]
  // ${lastCandle ? JSON.stringify(lastCandle) : 'Không có dữ liệu giá.'}

  // [CHỈ SỐ TÀI CHÍNH]
  // ${financeData ? JSON.stringify(financeData) : 'Không có dữ liệu tài chính.'}

  // [TIN TỨC MỚI NHẤT]
  // ${newsText}

  // - Trả lời HTML.
  // - Dùng <p>, <b>, <i>, <br>, <ul>, <li>, <a>.
  //   `.trim();

  //     const ai = await this.groq.chat.completions.create({
  //       model: 'llama-3.3-70b-versatile',
  //       messages: [
  //         {
  //           role: 'system',
  //           content: `${`
  // Bạn là AI chuyên gia chứng khoán Việt Nam của công ty Fireant.
  // Bạn CHỈ được trả lời các câu hỏi liên quan đến:
  // - chứng khoán
  // - cổ phiếu
  // - tài chính doanh nghiệp
  // - thị trường
  // - phân tích kỹ thuật / cơ bản
  // - kinh tế
  // - kinh doanh
  // - đầu tư vàng, bất động sản, crypto
  // - các công cụ tài chính
  // - các chỉ số tài chính
  // - gdp, lạm phát, lãi suất

  // NGUYÊN TẮC QUAN TRỌNG:
  // - Tin nhắn dài ngay sau system (message thứ 2) chỉ là NGỮ CẢNH DỮ LIỆU,
  //   KHÔNG phải câu hỏi của người dùng.
  // - KHÔNG được trả lời, KHÔNG được chào hỏi, KHÔNG được phản hồi lại message này.
  // - Chỉ được trả lời câu hỏi cuối cùng của người dùng.

  // QUY TẮC CHÀO HỎI:
  // - Nếu người dùng chỉ gõ các câu chào đơn thuần như: "hi", "hello", "xin chào", "chào bạn"
  //   thì hãy chào lại ngắn gọn và giới thiệu bạn là AI chứng khoán.
  // - Nếu câu hỏi KHÔNG PHẢI là chào đơn thuần thì trả lời thẳng vào nội dung.
  //   KHÔNG được chào lại, KHÔNG được mở đầu bằng "Xin chào".

  // NẾU câu hỏi KHÔNG liên quan đến chứng khoán → trả lời đúng mẫu sau:
  // "<p><b>Xin lỗi!</b> Tôi chỉ hỗ trợ các câu hỏi liên quan đến chứng khoán, cổ phiếu, tài chính và kinh tế. Vui lòng đặt câu hỏi phù hợp.</p>"

  // TUYỆT ĐỐI KHÔNG trả lời linh tinh về các chủ đề khác.
  // `}`,
  //         },
  //         { role: 'user', content: context },
  //         { role: 'user', content: question },
  //       ],
  //       temperature: 0.25,
  //     });

  //     const answerHtml = ai.choices[0].message.content;

  //     /** Save history */
  //     await this.aiStockRepository.save({
  //       userId,
  //       question,
  //       symbol: symbol || null,
  //       answer: answerHtml,
  //     });

  //     return {
  //       status: HttpStatusCode.OK,
  //       code: ResponseCode.SUCCESS,
  //       message: 'AI trả lời thành công',
  //       data: {
  //         symbol,
  //         answer: answerHtml,
  //       },
  //     };
  //   }
  async askStockAi(
    body: AiStockAskReqI,
  ): Promise<BaseResDataI<AiStockAskResI>> {
    const { userId, question } = body;
    const finsightResponse = await this.askFinSightBackend(body);
    if (finsightResponse) return finsightResponse;

    const groq = this.requireGroq();

    // Lấy 3 lịch sử gần nhất của user (nếu có)
    const lastHistories = userId
      ? await this.aiStockRepository.find({
          where: { userId },
          order: { createdAt: 'DESC' },
          take: 3,
        })
      : [];

    const orderedHistories = lastHistories.reverse();

    const historyMessages = orderedHistories.flatMap((h) => [
      {
        role: 'user' as const,
        content: h.question,
      },
      {
        role: 'assistant' as const,
        content: h.answer,
      },
    ]);

    const symbol = this.detectSymbol(question);

    /** CASE B — CÓ SYMBOL */
    // Nếu không có symbol → trả về data rỗng để không bị lỗi
    const [priceData, financeData, newsList] = symbol
      ? await Promise.all([
          this.fetchPrice(symbol),
          this.fetchFinance(symbol),
          this.fetchNews(symbol),
        ])
      : [null, null, []];

    const latestNews = newsList[0] || null;

    const newsSnippet = latestNews
      ? await this.buildNewsSnippet(latestNews)
      : null;

    const lastCandle = Array.isArray(priceData)
      ? priceData[priceData.length - 1]
      : null;

    const newsText = newsSnippet
      ? `
Tiêu đề: ${newsSnippet.title}
Tóm tắt: ${newsSnippet.summary}
Link: ${newsSnippet.link}
  `.trim()
      : 'Không có tin tức.';

    /** Build AI context */
    const context = `
DỮ LIỆU CỔ PHIẾU: ${symbol || 'Không tìm thấy mã'}

[GIÁ GẦN NHẤT]
${lastCandle ? JSON.stringify(lastCandle) : 'Không có dữ liệu giá.'}

[CHỈ SỐ TÀI CHÍNH]
${financeData ? JSON.stringify(financeData) : 'Không có dữ liệu tài chính.'}

[TIN TỨC MỚI NHẤT]
${newsText}

- Trả lời HTML.
- Dùng <p>, <b>, <i>, <br>, <ul>, <li>, <a>.
  `.trim();

    const ai = await groq.chat.completions.create({
      model: 'openai/gpt-oss-20b',
      messages: [
        {
          role: 'system',
          content: `${`
Bạn là Trợ lý ảo FinSight, chuyên gia hỗ trợ phân tích chứng khoán Việt Nam.
Bạn CHỈ được trả lời các câu hỏi liên quan đến:
- chứng khoán
- cổ phiếu
- tài chính doanh nghiệp
- thị trường
- phân tích kỹ thuật / cơ bản
- kinh tế
- kinh doanh
- đầu tư vàng, bất động sản, crypto
- liên quan đến các ngành và các công ty 
- các công cụ tài chính
- các chỉ số tài chính
- gdp, lạm phát, lãi suất
- kinh tế vĩ mô và vĩ mô thị trường Việt Nam
- Báo cáo ngành, báo cáo tài chính, báo cáo quản trị
- tài chính thế giới và các yếu tố kinh tế toàn cầu ảnh hưởng đến thị trường Việt Nam
- các ngành nghề thuộc phân loại ICB / VSIC
- doanh nghiệp niêm yết tại HOSE / HNX / UPCoM
- doanh nghiệp Việt Nam chưa niêm yết nhưng hoạt động trong các ngành kinh tế và có thông tin công khai

NGUYÊN TẮC QUAN TRỌNG:
- Tin nhắn dài ngay sau system (message thứ 2) chỉ là NGỮ CẢNH DỮ LIỆU, 
  KHÔNG phải câu hỏi của người dùng.
- KHÔNG được trả lời, KHÔNG được chào hỏi, KHÔNG được phản hồi lại message này.
- Chỉ được trả lời câu hỏi cuối cùng của người dùng.


QUY TẮC CHÀO HỎI:
- Nếu người dùng chỉ gõ các câu chào đơn thuần như: "hi", "hello", "xin chào", "chào bạn"
  thì hãy chào lại ngắn gọn và giới thiệu bạn là AI chứng khoán.
- Nếu câu hỏi KHÔNG PHẢI là chào đơn thuần thì trả lời thẳng vào nội dung. 
  KHÔNG được chào lại, KHÔNG được mở đầu bằng "Xin chào".

NẾU câu hỏi KHÔNG liên quan đến chứng khoán → trả lời đúng mẫu sau:
"<p><b>Xin lỗi!</b> Tôi chỉ hỗ trợ các câu hỏi liên quan đến chứng khoán, cổ phiếu, tài chính và kinh tế. Vui lòng đặt câu hỏi phù hợp.</p>"

TUYỆT ĐỐI KHÔNG trả lời linh tinh về các chủ đề khác.
`}`,
        },
        ...historyMessages,
        { role: 'user', content: context },
        { role: 'user', content: question },
      ],
      temperature: 0.25,
    });

    const answerHtml = ai.choices[0].message.content;

    /** Save history */
    await this.aiStockRepository.save({
      userId,
      question,
      symbol: symbol || null,
      answer: answerHtml,
    });

    return {
      status: HttpStatusCode.OK,
      code: ResponseCode.SUCCESS,
      message: 'AI trả lời thành công',
      data: {
        symbol,
        answer: answerHtml,
      },
    };
  }

  async getHistoryByUser(
    userId: number,
  ): Promise<BaseResDataI<AiStockAskResI[]>> {
    // 1. Validate userId
    if (!userId || isNaN(userId)) {
      return {
        status: HttpStatusCode.BAD_REQUEST,
        code: ResponseCode.ERROR,
        message: 'userId không hợp lệ',
        data: [],
      };
    }

    const history = await this.aiStockRepository.find({
      where: { userId },
      order: { createdAt: 'ASC' },
    });

    if (!history.length) {
      return {
        status: HttpStatusCode.OK,
        code: ResponseCode.SUCCESS,
        message: 'Không có lịch sử chat',
        data: [],
      };
    }

    return {
      status: HttpStatusCode.OK,
      code: ResponseCode.SUCCESS,
      message: 'Lấy lịch sử thành công',
      data: history.map((h) => ({
        question: h.question,
        answer: h.answer,
        symbol: h.symbol,
        createdAt: h.createdAt,
      })),
    };
  }
}
