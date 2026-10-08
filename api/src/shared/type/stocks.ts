import { BaseResI } from './base';

export interface StockI {
  code: string;
  name: string;
//   exchange?: string;
//   marketCap?: number;
  industryId?: number;
}

export interface StockReqI extends StockI {}

export interface StockResI extends BaseResI, StockI {}
