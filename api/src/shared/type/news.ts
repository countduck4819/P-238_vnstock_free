import { BaseResI } from './base';

export interface NewsI {
  news_id: string;
  news_title: string;
  news_sub_title?: string;
  news_short_content?: string;
  news_full_content?: string;
  news_image_url?: string;
  news_source_link?: string;
  public_date?: string;
  slug?: string;
  symbol?: string;
}

export interface NewsReqI extends NewsI {}

export interface NewsResI extends BaseResI, NewsI {}
