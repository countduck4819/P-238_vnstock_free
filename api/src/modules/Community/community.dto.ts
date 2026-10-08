import { IsNotEmpty, IsOptional, IsString, IsNumber } from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';

export class CreateCommunityPostDto {
  @ApiProperty({ required: false })
  @IsOptional()
  @IsNumber()
  userId?: number;

  @ApiProperty({ required: false })
  @IsOptional()
  @IsString()
  authorName?: string;

  @ApiProperty({ required: false })
  @IsOptional()
  @IsString()
  authorAvatar?: string;

  @ApiProperty({ required: false })
  @IsOptional()
  @IsString()
  authorRole?: string;

  @ApiProperty({ required: false })
  @IsOptional()
  @IsString()
  authorBadge?: string;

  @ApiProperty({ required: false })
  @IsOptional()
  @IsString()
  title?: string;

  @ApiProperty({ required: true })
  @IsNotEmpty()
  @IsString()
  content: string;

  @ApiProperty({ required: false })
  @IsOptional()
  @IsString()
  symbol?: string;

  @ApiProperty({ required: false })
  @IsOptional()
  @IsString()
  stance?: string;

  @ApiProperty({ required: false })
  @IsOptional()
  @IsNumber()
  targetPrice?: number;

  @ApiProperty({ required: false })
  @IsOptional()
  @IsNumber()
  stopLossPrice?: number;

  @ApiProperty({ required: false, default: 'hot' })
  @IsOptional()
  @IsString()
  category?: string;

  @ApiProperty({ required: false })
  @IsOptional()
  @IsString()
  sector?: string;

  @ApiProperty({ required: false })
  @IsOptional()
  @IsString()
  imageUrl?: string;
}

export class CreateCommunityCommentDto {
  @ApiProperty({ required: true })
  @IsNotEmpty()
  @IsString()
  content: string;

  @ApiProperty({ required: false })
  @IsOptional()
  @IsNumber()
  userId?: number;

  @ApiProperty({ required: false })
  @IsOptional()
  @IsString()
  authorName?: string;

  @ApiProperty({ required: false })
  @IsOptional()
  @IsString()
  authorAvatar?: string;
}

export class GetCommunityPostsQueryDto {
  @ApiProperty({ required: false, default: 1 })
  @IsOptional()
  page?: number;

  @ApiProperty({ required: false, default: 20 })
  @IsOptional()
  limit?: number;

  @ApiProperty({ required: false })
  @IsOptional()
  @IsString()
  category?: string;

  @ApiProperty({ required: false })
  @IsOptional()
  @IsString()
  sector?: string;

  @ApiProperty({ required: false })
  @IsOptional()
  @IsString()
  symbol?: string;

  @ApiProperty({ required: false })
  @IsOptional()
  @IsString()
  keyword?: string;

  @ApiProperty({ required: false })
  @IsOptional()
  userId?: number;
}
