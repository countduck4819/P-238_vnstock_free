import { ApiProperty } from '@nestjs/swagger';
import { IsNotEmpty, IsString } from 'class-validator';
import { IndustryReqI } from 'src/shared';


export class IndustryDto implements IndustryReqI {
  @ApiProperty({
    description: 'Tên ngành (duy nhất)',
    example: 'Ngân hàng',
  })
  @IsString()
  @IsNotEmpty()
  name: string;
}
