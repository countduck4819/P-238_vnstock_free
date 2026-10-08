import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';

export class UploadFileDto {
  @ApiProperty({ type: String, description: 'Base64 string or file URL' })
  file: string;

  @ApiPropertyOptional({ type: String, description: 'Optional folder name' })
  folder?: string;
}
