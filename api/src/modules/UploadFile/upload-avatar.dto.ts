import { ApiProperty } from '@nestjs/swagger';

export class UploadAvatarDto {
  @ApiProperty({ type: String, description: 'Base64 string or file URL' })
  avatar: string;
}
