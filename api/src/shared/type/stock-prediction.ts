import { BaseResI } from './base';

export interface StockPredictionI {
  ticker: string;
  lastClosePrice: number;
  predictedPrice: number;
  pEnsemble?: number | null;
  chartPath?: string | null;
  predictedOn: Date;
}

export interface StockPredictionReqI extends StockPredictionI {}

export interface StockPredictionResI extends BaseResI, StockPredictionI {}
