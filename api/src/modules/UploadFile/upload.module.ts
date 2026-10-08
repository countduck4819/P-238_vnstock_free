import { Module } from '@nestjs/common';

import { UploadController } from './upload.controller';
import { UploadToken } from 'src/shared';
import { UploadService } from './upload.service';

@Module({
  imports: [],
  controllers: [UploadController],
  providers: [
    {
      provide: UploadToken,
      useClass: UploadService,
    },
  ],
  exports: [UploadToken],
})
export class UploadModule {}
