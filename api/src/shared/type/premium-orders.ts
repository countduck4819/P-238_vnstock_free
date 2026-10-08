import { PremiumOrderStatus } from "../enum/TypeEnum.enum";
import { BaseResI } from "./base";


export interface PremiumOrderI {
  orderCode: string;
  userId: number;
  amount: number;
  status: PremiumOrderStatus
  transactionId?: string;
  paymentMethod?: string;
}

export interface PremiumOrderReqI extends PremiumOrderI {}

export interface PremiumOrderResI extends BaseResI, PremiumOrderI {}
