import { ApiProperty } from '@nestjs/swagger';
import { IsNotEmpty, IsString, IsNumber, IsOptional } from 'class-validator';
import { StockReqI } from 'src/shared';

export class StockDto implements StockReqI {
  @ApiProperty({
    description: 'Mã cổ phiếu (duy nhất)',
    example: 'FPT',
  })
  @IsString()
  @IsNotEmpty()
  code: string;

  @ApiProperty({
    description: 'Tên công ty / cổ phiếu',
    example: 'Công ty CP FPT',
  })
  @IsString()
  @IsNotEmpty()
  name: string;

  //   @ApiProperty({
  //     description: 'Sàn giao dịch',
  //     example: 'HOSE',
  //     required: false,
  //   })
  //   @IsString()
  //   @IsOptional()
  //   exchange?: string;

  //   @ApiProperty({
  //     description: 'Vốn hóa thị trường',
  //     example: 5000000000,
  //     required: false,
  //   })
  //   @IsNumber()
  //   @IsOptional()
  //   marketCap?: number;

  @ApiProperty({
    name: 'industryId',
    description: 'ID ngành nghề',
    example: 1,
    required: false,
  })
  @IsNumber()
  @IsOptional()
  industryId?: number;
}
