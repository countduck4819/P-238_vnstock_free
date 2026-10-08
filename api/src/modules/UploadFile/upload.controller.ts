// import {
//   Controller,
//   Post,
//   UploadedFile,
//   UseInterceptors,
//   Body,
//   Inject,
// } from '@nestjs/common';
// import { ApiConsumes, ApiBody, ApiBearerAuth } from '@nestjs/swagger';
// import { UploadService } from './upload.service';
// import type { MulterFile } from 'src/shared';
// import { UploadToken } from 'src/shared';
// import { Public } from 'src/shared/decorator/is-public.decorator';
// import { FastifyMulterModule, FileInterceptor } from '@nest-lab/fastify-multer';

// class UploadFileDto {
//   folder?: string;
// }

// @ApiBearerAuth()
// @Controller('upload')
// @Public()
// export class UploadController {
//   constructor(
//     @Inject(UploadToken)
//     private readonly uploadService: UploadService,
//   ) {}

//   @Post('avatar')
//   @ApiConsumes('multipart/form-data')
//   @ApiBody({
//     schema: {
//       type: 'object',
//       properties: {
//         avatar: { type: 'string', format: 'binary' },
//       },
//     },
//   })
//   @UseInterceptors(FileInterceptor('avatar'))
//   async uploadAvatar(@UploadedFile() file: FastifyMulterModule) {
//     return this.uploadService.uploadAvatar(file.buffer);
//   }

//   @Post('file')
//   @ApiConsumes('multipart/form-data')
//   @ApiBody({
//     schema: {
//       type: 'object',
//       properties: {
//         file: { type: 'string', format: 'binary' },
//         folder: { type: 'string', nullable: true },
//       },
//     },
//   })
//   @UseInterceptors(FileInterceptor('file'))
//   async uploadFile(
//     @UploadedFile() file: MulterFile,
//     @Body() body: UploadFileDto,
//   ) {
//     return this.uploadService.uploadFile(file.buffer, body.folder);
//   }
// }

import {
  Controller,
  Post,
  UploadedFile,
  UseInterceptors,
  Body,
  Inject,
  BadRequestException,
} from '@nestjs/common';
import { FileInterceptor } from '@nest-lab/fastify-multer';
import { ApiConsumes, ApiBody, ApiBearerAuth } from '@nestjs/swagger';
import { UploadService, UploadResponse } from './upload.service';
import { UploadToken } from 'src/shared';
import { Public } from 'src/shared/decorator/is-public.decorator';

// Định nghĩa type cho file từ Fastify Multer
type FastifyMulterFile = {
  fieldname: string;
  originalname: string;
  encoding: string;
  mimetype: string;
  buffer: Buffer;
  size: number;
};

class UploadFileDto {
  folder?: string;
}

@ApiBearerAuth()
@Controller('upload')
@Public()
export class UploadController {
  constructor(
    @Inject(UploadToken)
    private readonly uploadService: UploadService,
  ) {}

  @Post('avatar')
  @ApiConsumes('multipart/form-data')
  @ApiBody({
    schema: {
      type: 'object',
      properties: {
        avatar: { type: 'string', format: 'binary' },
      },
    },
  })
  @UseInterceptors(FileInterceptor('avatar'))
  async uploadAvatar(@UploadedFile() file: FastifyMulterFile) {
    if (!file) throw new BadRequestException('Không nhận được file avatar');

    const result: UploadResponse = await this.uploadService.uploadAvatar(
      file.buffer,
    );

    return {
      status: result.status,
      code: result.code,
      message: result.message,
      data: result.data,
    };
  }

  @Post('file')
  @ApiConsumes('multipart/form-data')
  @ApiBody({
    schema: {
      type: 'object',
      properties: {
        file: { type: 'string', format: 'binary' },
        folder: { type: 'string', nullable: true },
      },
    },
  })
  @UseInterceptors(FileInterceptor('file'))
  async uploadFile(
    @UploadedFile() file: FastifyMulterFile,
    @Body() body: UploadFileDto,
  ) {
    if (!file) throw new BadRequestException('Không nhận được file');

    const result: UploadResponse = await this.uploadService.uploadFile(
      file.buffer,
      body.folder,
    );

    return {
      status: result.status,
      code: result.code,
      message: result.message,
      data: result.data,
    };
  }
}
