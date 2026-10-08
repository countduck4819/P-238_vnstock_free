import { ApiProperty } from '@nestjs/swagger';
import { IsOptional, IsString } from 'class-validator';
import { NewsReqI } from 'src/shared';

export class NewsDto implements NewsReqI {
  @ApiProperty()
  @IsString()
  news_id: string;

  @ApiProperty()
  @IsString()
  news_title: string;

  @ApiProperty({ required: false })
  @IsOptional()
  @IsString()
  news_short_content?: string;

  @ApiProperty({ required: false })
  @IsOptional()
  @IsString()
  news_full_content?: string;

  @ApiProperty({ required: false })
  @IsOptional()
  @IsString()
  public_date?: string;

  @ApiProperty({ required: false })
  @IsOptional()
  @IsString()
  symbol?: string;
}
