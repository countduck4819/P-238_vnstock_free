import {
  IsIn,
  IsInt,
  IsNotEmpty,
  IsNumber,
  IsOptional,
  IsString,
  Max,
  MaxLength,
  Min,
} from 'class-validator';
import { Transform, Type } from 'class-transformer';
import { ApiProperty } from '@nestjs/swagger';

export const POST_STANCES = ['BUY', 'SELL', 'HOLD', 'ANALYSIS'] as const;
export const POST_CATEGORIES = [
  'hot',
  'signal',
  'technical',
  'fundamental',
  'qa',
] as const;

const trim = ({ value }: { value: unknown }) =>
  typeof value === 'string' ? value.trim() : value;

// Author identity is never accepted from the client: it is resolved from the
// access token on the server.
export class CreateCommunityPostDto {
  @ApiProperty({ required: false })
  @IsOptional()
  @IsString()
  @MaxLength(255)
  @Transform(trim)
  title?: string;

  @ApiProperty({ required: true })
  @Transform(trim)
  @IsNotEmpty()
  @IsString()
  @MaxLength(5000)
  content: string;

  @ApiProperty({ required: false })
  @IsOptional()
  @IsString()
  @MaxLength(20)
  @Transform(({ value }: { value: unknown }) =>
    typeof value === 'string' ? value.trim().toUpperCase() || undefined : value,
  )
  symbol?: string;

  @ApiProperty({ required: false, enum: POST_STANCES })
  @IsOptional()
  @IsIn(POST_STANCES)
  stance?: (typeof POST_STANCES)[number];

  @ApiProperty({ required: false })
  @IsOptional()
  @IsNumber()
  @Min(0)
  targetPrice?: number;

  @ApiProperty({ required: false })
  @IsOptional()
  @IsNumber()
  @Min(0)
  stopLossPrice?: number;

  @ApiProperty({ required: false, default: 'hot', enum: POST_CATEGORIES })
  @IsOptional()
  @IsIn(POST_CATEGORIES)
  category?: (typeof POST_CATEGORIES)[number];

  @ApiProperty({ required: false })
  @IsOptional()
  @IsString()
  @MaxLength(100)
  sector?: string;

  @ApiProperty({ required: false })
  @IsOptional()
  @IsString()
  @MaxLength(2000)
  imageUrl?: string;
}

export class CreateCommunityCommentDto {
  @ApiProperty({ required: true })
  @Transform(trim)
  @IsNotEmpty()
  @IsString()
  @MaxLength(2000)
  content: string;
}

export class GetCommunityPostsQueryDto {
  @ApiProperty({ required: false, default: 1 })
  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(1)
  page?: number;

  @ApiProperty({ required: false, default: 20 })
  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(1)
  @Max(50)
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

  @ApiProperty({
    required: false,
    description: 'Chỉ lấy bài của thành viên này',
  })
  @IsOptional()
  @Type(() => Number)
  @IsInt()
  authorId?: number;
}

export class StartConversationDto {
  @ApiProperty({ required: true })
  @Type(() => Number)
  @IsInt()
  @Min(1)
  recipientId: number;
}

export class SendMessageDto {
  @ApiProperty({ required: true })
  @Transform(trim)
  @IsNotEmpty()
  @IsString()
  @MaxLength(2000)
  content: string;
}

export class GetMessagesQueryDto {
  @ApiProperty({
    required: false,
    description: 'Lấy các tin nhắn cũ hơn tin nhắn có id này',
  })
  @IsOptional()
  @Type(() => Number)
  @IsInt()
  beforeId?: number;

  @ApiProperty({ required: false, default: 30 })
  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(1)
  @Max(100)
  limit?: number;
}

export class SearchMembersQueryDto {
  @ApiProperty({ required: false })
  @IsOptional()
  @IsString()
  @MaxLength(100)
  keyword?: string;
}
