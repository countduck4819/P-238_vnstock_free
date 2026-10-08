import { StockPredictionEntity } from 'src/modules/StockPrediction/stock-prediction.entities';
import {
  AiStockAskReqI,
  AiStockAskResI,
  AiStockHistoryReqI,
  AiStockHistoryResI,
} from './ai-stock';
import { BaseResDataI } from './base';
import { IndustryReqI, IndustryResI } from './industries';
import { NewsReqI, NewsResI } from './news';
import { StockPredictionResI } from './stock-prediction';
import {
  StockRecommendationReqI,
  StockRecommendationResI,
} from './stock-recommendations';
import { StockReqI, StockResI } from './stocks';
import { UserReqI, UserResI } from './users';

export interface BaseServicesI<RequestI, ResponseI> {
  paginate: (
    condition?: Partial<Record<keyof RequestI, any>>,
    page?: number,
    limit?: number,
    searchFilters?: Partial<Record<keyof RequestI, any>>,
  ) => Promise<BaseResDataI<ResponseI[] | null>>;
  findOne: (id: number) => Promise<BaseResDataI<ResponseI[] | null>>;
  find: (params?: any) => Promise<BaseResDataI<ResponseI[] | null>>;
  create: (data: RequestI) => Promise<BaseResDataI<ResponseI[] | null>>;
  updateOne: (
    id: number,
    data: RequestI,
  ) => Promise<BaseResDataI<ResponseI[] | null>>;
  softDelete: (id: number) => Promise<BaseResDataI<any>>;
  getJsonData: (filename: string) => Promise<BaseResDataI<any>>;
}

export interface UsersServiceI extends BaseServicesI<UserReqI, UserResI> {}

export interface AuthServiceI extends BaseServicesI<UserReqI, UserResI> {
  loginWithPassword: (data: any) => Promise<BaseResDataI<any>>;
  refreshToken: (tokenData: {
    refreshToken: string;
  }) => Promise<BaseResDataI<any>>;
  logout: (userId: number) => Promise<BaseResDataI<any>>;
}

export interface IndustryServiceI
  extends BaseServicesI<IndustryReqI, IndustryResI> {}

export interface StocksServiceI extends BaseServicesI<StockReqI, StockResI> {
  findByIndustry: (industryId: number) => Promise<any>;
}

export interface NewsServiceI extends BaseServicesI<NewsReqI, NewsResI> {}

/** Service interface cho StockRecommendations */
export interface StockRecommendationsServiceI
  extends BaseServicesI<StockRecommendationReqI, StockRecommendationResI> {
  getAvailableStocks: () => Promise<BaseResDataI<any>>;
}

export interface AiStockServiceI
  extends BaseServicesI<AiStockHistoryReqI, AiStockHistoryResI> {
  askStockAi: (
    data: AiStockAskReqI,
  ) => Promise<BaseResDataI<AiStockAskResI | null>>;
}

export interface StockPredictionServiceI {
  importFromJson(): Promise<any>;

  savePrediction(dto: {
    ticker: string;
    lastClosePrice: number;
    predictedPrice: number;
    chartPath?: string | null;
  }): Promise<any>;

  getLatest(ticker: string): Promise<BaseResDataI<StockPredictionResI | null>>;
}
