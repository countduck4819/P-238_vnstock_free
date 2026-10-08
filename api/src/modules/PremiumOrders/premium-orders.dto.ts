import { ApiProperty } from '@nestjs/swagger';
import {
  IsNotEmpty,
  IsNumber,
  IsOptional,
  IsString,
  IsEnum,
} from 'class-validator';
import { PremiumOrderStatus } from 'src/shared';

export class CreatePremiumOrderDto {
  @ApiProperty({ description: 'User ID thanh toán', example: 12 })
  @IsNotEmpty()
  @IsNumber()
  userId: number;

  @ApiProperty({ description: 'Số tiền Premium', example: 99000 })
  @IsOptional()
  amount?: number;
}

export class UpdatePremiumOrderStatusDto {
  @ApiProperty({
    description: 'Trạng thái hóa đơn',
    enum: PremiumOrderStatus,
    example: PremiumOrderStatus.PAID,
  })
  @IsOptional()
  @IsEnum(PremiumOrderStatus)
  status?: PremiumOrderStatus;

  @ApiProperty({
    description: 'Mã giao dịch PayOS',
    required: false,
  })
  @IsOptional()
  @IsString()
  transactionId?: string;

  @ApiProperty({
    description: 'Phương thức thanh toán',
    required: false,
  })
  @IsOptional()
  @IsString()
  paymentMethod?: string;
}
