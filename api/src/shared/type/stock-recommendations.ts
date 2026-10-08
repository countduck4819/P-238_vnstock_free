import { StockRecommendationStatus } from '../enum/TypeEnum.enum';
import { BaseResI } from './base';


/** Dữ liệu chính */
export interface StockRecommendationI {
  stockId: number;
  buyPrice: number;
  targetPrice: number;
  stopLossPrice: number;
  status: StockRecommendationStatus;
  note?: string;
  isActive?: boolean;
  closedAt?: Date | null;
}

/** Request body */
export interface StockRecommendationReqI extends StockRecommendationI {}

/** Response trả về cho client */
export interface StockRecommendationResI
  extends BaseResI,
    StockRecommendationI {}
