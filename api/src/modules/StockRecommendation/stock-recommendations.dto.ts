import { ApiProperty } from '@nestjs/swagger';
import {
  IsNotEmpty,
  IsNumber,
  IsOptional,
  IsString,
  IsEnum,
  IsBoolean,
  IsDateString,
} from 'class-validator';
import { StockRecommendationStatus } from 'src/shared';


export class StockRecommendationDto {
  @ApiProperty({ description: 'ID cổ phiếu', example: 1 })
  @IsNotEmpty()
  stockId: number;

  @ApiProperty({ description: 'Giá mua', example: 24.5 })
  @IsNumber()
  buyPrice: number;

  @ApiProperty({ description: 'Giá chốt lời', example: 28 })
  @IsNumber()
  targetPrice: number;

  @ApiProperty({ description: 'Giá cắt lỗ', example: 22 })
  @IsNumber()
  stopLossPrice: number;

  @ApiProperty({
    description: 'Trạng thái khuyến nghị',
    enum: StockRecommendationStatus,
    default: StockRecommendationStatus.ACTIVE,
  })
  @IsOptional()
  @IsEnum(StockRecommendationStatus)
  status?: StockRecommendationStatus;

  @ApiProperty({
    description: 'Ghi chú',
    example: 'Khuyến nghị mua vùng 24-25',
  })
  @IsOptional()
  @IsString()
  note?: string;

  @ApiProperty({ description: 'Trạng thái hiển thị', example: true })
  @IsOptional()
  @IsBoolean()
  isActive?: boolean;

  @ApiProperty({
    description: 'Thời điểm đạt target hoặc cắt lỗ',
    example: '2025-11-12T10:30:00Z',
  })
  @IsOptional()
  @IsDateString()
  closedAt?: Date;
}
