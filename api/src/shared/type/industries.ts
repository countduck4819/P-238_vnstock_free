import { BaseResI } from './base';

export interface IndustryI {
  name: string;
}

export interface IndustryReqI extends IndustryI {}

export interface IndustryResI extends BaseResI, IndustryI {}
