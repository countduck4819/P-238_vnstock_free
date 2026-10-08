import { HttpStatusCode, ResponseCode } from '../enum/TypeEnum.enum';

export interface BaseI {
  createdAt: Date;
  createdBy?: number | null;
  modifiedAt?: Date | null;
  modifiedBy?: number | null;
  deletedAt?: Date | null;
  deletedBy?: number | null;
  active: boolean;
}

export interface BaseReqI {}

export interface BaseResI extends BaseI {
  id: number;
}

export interface MetaDatabase {
  page?: number;
  limit?: number;
  total?: number;
  totalPages?: number;
}

export interface BaseResDataI<DataI> {
  status?: HttpStatusCode;
  code?: ResponseCode;
  message?: string;
  data?: DataI;
  meta?: MetaDatabase;
}
