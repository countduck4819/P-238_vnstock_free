import {
  CanActivate,
  ExecutionContext,
  ForbiddenException,
  Injectable,
} from '@nestjs/common';
import { AccountType, UserRole } from 'src/shared';

@Injectable()
export class WaveV6PremiumGuard implements CanActivate {
  canActivate(context: ExecutionContext): boolean {
    const user = context.switchToHttp().getRequest().user;
    if (user?.role === UserRole.ADMIN) return true;
    if (
      user?.role === UserRole.USER &&
      user?.accountType === AccountType.PREMIUM
    ) {
      return true;
    }
    throw new ForbiddenException(
      'Long-term advisory is available to Premium accounts only.',
    );
  }
}
