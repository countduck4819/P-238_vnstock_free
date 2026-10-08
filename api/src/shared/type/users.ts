import { AccountType, Gender, UserRole } from '../enum/TypeEnum.enum';
import { BaseResI } from './base';

export interface UserI {
  username: string;
  email: string;
  address?: string;
  password: string;
  fullName?: string;
  role?: UserRole;
  accountType?: AccountType;
  avatar?: string;
  gender?: Gender;
  citizenId?: string;
  watchList: string[];
}

export interface UserReqI extends UserI {}

export interface UserResI extends BaseResI, UserI {}
