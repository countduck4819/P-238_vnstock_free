import { ExecutionContext, Injectable } from "@nestjs/common";
import { Reflector } from "@nestjs/core";
import { AuthGuard } from "@nestjs/passport";
import { IS_PUBLIC_KEY } from "src/shared/decorator/is-public.decorator";

@Injectable()
export class JwtAuthGuard extends AuthGuard("jwt") {
  constructor(private reflector: Reflector) {
    super();
  }

  async canActivate(context: ExecutionContext): Promise<boolean> {
    const isPublic = this.reflector.getAllAndOverride<boolean>(IS_PUBLIC_KEY, [
      context.getHandler(),
      context.getClass(),
    ]);

    if (!isPublic) {
      return super.canActivate(context) as Promise<boolean>;
    }

    // Public routes still resolve `req.user` when a valid token is sent, so
    // they can personalise the response (e.g. "liked by me"). An invalid or
    // missing token never blocks a public route.
    const request = context.switchToHttp().getRequest();
    if (request?.headers?.authorization) {
      try {
        await super.canActivate(context);
      } catch {
        request.user = undefined;
      }
    }
    return true;
  }
}
