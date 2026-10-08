import {
  CanActivate,
  ExecutionContext,
  ForbiddenException,
  Injectable,
} from '@nestjs/common';
import { AccountType, UserRole } from 'src/shared';

/**
 * The global RolesGuard currently permits every normal user once authenticated.
 * Keep the H120 advisory entitlement explicit so this probability feed cannot
 * accidentally become available to free accounts.
 */
@Injectable()
export class WaveH120PremiumGuard implements CanActivate {
  canActivate(context: ExecutionContext): boolean {
    const user = context.switchToHttp().getRequest().user;

    if (user?.role === UserRole.ADMIN) {
      return true;
    }

    if (
      user?.role === UserRole.USER &&
      user?.accountType === AccountType.PREMIUM
    ) {
      return true;
    }

    throw new ForbiddenException(
      'Short-term advisory is available to Premium accounts only.',
    );
  }
}
