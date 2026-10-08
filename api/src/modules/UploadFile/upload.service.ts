// import { Injectable } from '@nestjs/common';
// import cloudinary from 'cloudinary.config';
// import { HttpStatusCode, ResponseCode } from 'src/shared';
// export interface UploadResponse {
//   status: number;
//   code: string;
//   message: string;
//   data: {
//     url: string;
//     public_id: string;
//   } | null;
// }
// @Injectable()
// export class UploadService {
//   private async uploadBuffer(
//     file: Buffer,
//     folder: string,
//     options?: Partial<{
//       width: number;
//       height: number;
//       crop: string;
//       quality: string;
//       fetch_format: string;
//     }>,
//   ) {
//     if (!file) {
//       return {
//         status: HttpStatusCode.BAD_REQUEST,
//         code: ResponseCode.ERROR,
//         message: 'Không thấy file',
//         data: null,
//       };
//     }

//     return new Promise((resolve) => {
//       const stream = cloudinary.uploader.upload_stream(
//         {
//           folder,
//           width: options?.width,
//           height: options?.height,
//           crop: options?.crop || 'limit',
//           quality: options?.quality || 'auto',
//           fetch_format: options?.fetch_format || 'auto',
//           secure: true,
//         },
//         (error, result) => {
//           if (error) {
//             resolve({
//               status: HttpStatusCode.INTERNAL_ERROR,
//               code: ResponseCode.ERROR,
//               message: error.message,
//               data: null,
//             });
//           } else {
//             resolve({
//               status: HttpStatusCode.OK,
//               code: ResponseCode.SUCCESS,
//               message: `Upload ${folder} thành công`,
//               data: {
//                 url: result?.secure_url,
//                 public_id: result?.public_id,
//               },
//             });
//           }
//         },
//       );

//       stream.end(file);
//     });
//   }

//   async uploadAvatar(file: Buffer) {
//     return this.uploadBuffer(file, 'avatars', { width: 500, height: 500 });
//   }

//   async uploadFile(
//     file: Buffer,
//     folder = 'files',
//     options?: Partial<{
//       width: number;
//       height: number;
//       crop: string;
//       quality: string;
//       fetch_format: string;
//     }>,
//   ) {
//     return this.uploadBuffer(file, folder, options);
//   }
// }

import { Injectable } from '@nestjs/common';
import cloudinary from 'cloudinary.config';
import { HttpStatusCode, ResponseCode } from 'src/shared';

export interface UploadResponse {
  status: number;
  code: ResponseCode;
  message: string;
  data: {
    url: string;
    public_id: string;
  } | null;
}

@Injectable()
export class UploadService {
  private async uploadBuffer(
    file: Buffer,
    folder: string,
    options?: Partial<{
      width: number;
      height: number;
      crop: string;
      quality: string;
      fetch_format: string;
    }>,
  ): Promise<UploadResponse> {
    if (!file) {
      return {
        status: HttpStatusCode.BAD_REQUEST,
        code: ResponseCode.ERROR,
        message: 'Không thấy file',
        data: null,
      };
    }

    return new Promise<UploadResponse>((resolve) => {
      const stream = cloudinary.uploader.upload_stream(
        {
          folder,
          width: options?.width,
          height: options?.height,
          crop: options?.crop || 'limit',
          quality: options?.quality || 'auto',
          fetch_format: options?.fetch_format || 'auto',
          secure: true,
        },
        (error, result) => {
          if (error) {
            resolve({
              status: HttpStatusCode.INTERNAL_ERROR,
              code: ResponseCode.ERROR,
              message: error.message,
              data: null,
            });
          } else {
            resolve({
              status: HttpStatusCode.OK,
              code: ResponseCode.SUCCESS,
              message: `Upload ${folder} thành công`,
              data: {
                url: result?.secure_url!,
                public_id: result?.public_id!,
              },
            });
          }
        },
      );

      stream.end(file);
    });
  }

  async uploadAvatar(file: Buffer): Promise<UploadResponse> {
    return this.uploadBuffer(file, 'avatars', { width: 500, height: 500 });
  }

  async uploadFile(
    file: Buffer,
    folder = 'files',
    options?: Partial<{
      width: number;
      height: number;
      crop: string;
      quality: string;
      fetch_format: string;
    }>,
  ): Promise<UploadResponse> {
    return this.uploadBuffer(file, folder, options);
  }
}
