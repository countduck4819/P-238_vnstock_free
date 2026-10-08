import { BaseResI } from './base';

// Entity data
export interface AiStockHistoryI {
  userId: number;
  question: string;
  answer: string | null;
  symbol?: string | null;
}

export interface AiStockHistoryReqI extends AiStockHistoryI {}

export interface AiStockHistoryResI extends BaseResI, AiStockHistoryI {}

// Request cho AI
export interface AiStockAskReqI {
  userId: number;
  question: string;
}

// Data AI trả về
export interface AiStockAskResI {
  symbol: string | null;
  answer: string | null;
}
