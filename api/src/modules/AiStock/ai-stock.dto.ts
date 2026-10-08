import { ApiProperty } from '@nestjs/swagger';
import { IsNotEmpty, IsNumber, IsOptional, IsString } from 'class-validator';
import { AiStockAskReqI, AiStockHistoryReqI } from 'src/shared';

// DTO cho CRUD lịch sử (create/update)
export class AiStockHistoryDto implements AiStockHistoryReqI {
  @ApiProperty({ example: 1 })
  @IsNumber()
  userId: number;

  @ApiProperty({
    example: 'Hôm nay VCB giá bao nhiêu?',
  })
  @IsString()
  @IsNotEmpty()
  question: string;

  @ApiProperty({
    example: '<p>VCB hiện đang giao dịch quanh vùng...</p>',
    required: false,
  })
  @IsString()
  @IsOptional()
  answer: string | null;

  @ApiProperty({
    example: 'VCB',
    required: false,
  })
  @IsString()
  @IsOptional()
  symbol?: string;
}

// DTO cho endpoint /ask
export class AiStockAskDto implements AiStockAskReqI {
  @ApiProperty({ example: 1 })
  @IsNumber()
  userId: number;

  @ApiProperty({
    example: 'Đánh giá nhanh cổ phiếu VCB giúp tôi?',
  })
  @IsString()
  @IsNotEmpty()
  question: string;
}
