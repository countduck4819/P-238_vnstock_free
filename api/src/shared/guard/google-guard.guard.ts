import {
  ExecutionContext,
  Injectable,
  ServiceUnavailableException,
} from '@nestjs/common';
import { AuthGuard } from '@nestjs/passport';

@Injectable()
export class GoogleAuthGuard extends AuthGuard('google') {
  canActivate(context: ExecutionContext) {
    if (!process.env.GOOGLE_CLIENT_ID || !process.env.GOOGLE_CLIENT_SECRET) {
      throw new ServiceUnavailableException(
        'Google sign-in is not configured for this deployment.',
      );
    }
    return super.canActivate(context);
  }
}

// google-guard.guard.ts
// import { Injectable, ExecutionContext } from '@nestjs/common';
// import { AuthGuard } from '@nestjs/passport';

// @Injectable()
// export class GoogleAuthGuard extends AuthGuard('google') {
//   async canActivate(context: ExecutionContext): Promise<boolean> {
//     const result = (await super.canActivate(context)) as boolean;
//     const request = context.switchToHttp().getRequest();
//     await super.logIn(request);
//     return result;
//   }
// }
