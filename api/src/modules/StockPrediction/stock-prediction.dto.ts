import { ApiProperty } from '@nestjs/swagger';
import { IsString, IsNumber, IsOptional } from 'class-validator';

export class StockPredictionDto {
  @ApiProperty({ example: 'VCB' })
  @IsString()
  ticker: string;

  @ApiProperty({ example: 92700 })
  @IsNumber()
  lastClosePrice: number;

  @ApiProperty({ example: 95560.22 })
  @IsNumber()
  predictedPrice: number;

  @ApiProperty({ example: 0.6974601632287041, required: false, nullable: true })
  @IsOptional()
  @IsNumber()
  pEnsemble?: number | null;

  @ApiProperty({ example: 'charts/VCB_20251117_120011.png' })
  @IsString()
  chartPath: string;
}
