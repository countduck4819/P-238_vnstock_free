// import {
//   CanActivate,
//   ExecutionContext,
//   Injectable,
//   ForbiddenException,
//   SetMetadata,
// } from '@nestjs/common';
// import { Reflector } from '@nestjs/core';
// import { ROLES_GUARD_KEY } from '../decorator/roles.decorator';
// import { AccountType, UserRole } from '../enum/TypeEnum.enum';
// import { IS_PUBLIC_KEY } from '../decorator/is-public.decorator';

import { CanActivate, ExecutionContext, ForbiddenException, Injectable } from "@nestjs/common";
import { AccountType, UserRole } from "../enum/TypeEnum.enum";
import { ROLES_GUARD_KEY } from "../decorator/roles.decorator";
import { Reflector } from "@nestjs/core";
import { IS_PUBLIC_KEY } from "../decorator/is-public.decorator";

// @Injectable()
// export class RolesGuard implements CanActivate {
//   constructor(private reflector: Reflector) {}

//   canActivate(context: ExecutionContext): boolean {
//     const isPublic = this.reflector.getAllAndOverride<boolean>(IS_PUBLIC_KEY, [
//       context.getHandler(),
//       context.getClass(),
//     ]);
//     if (isPublic) return true;

//     const roles = this.reflector.getAllAndOverride<UserRole[]>(
//       ROLES_GUARD_KEY,
//       [context.getHandler(), context.getClass()],
//     );

//     if (!roles || roles.length === 0) return true;

//     const req = context.switchToHttp().getRequest();
//     const user = req.user;

//     if (!user) throw new ForbiddenException('Bạn cần đăng nhập');

//     // Admin luôn pass
//     if (user.role === UserRole.ADMIN) return true;

//     // User premium pass
//     if (user.role === UserRole.USER && user.accountType === AccountType.PREMIUM)
//       return true;

//     // User free / normal pass (nếu muốn)
//     if (
//       user.role === UserRole.USER ||
//       (user.role === UserRole.USER && user.accountType === AccountType.FREE)
//     )
//       return true;

//     throw new ForbiddenException(
//       'Chỉ admin hoặc user premium/free mới được truy cập',
//     );
//   }
// }

@Injectable()
export class RolesGuard implements CanActivate {
  constructor(private reflector: Reflector) {}

  canActivate(context: ExecutionContext): boolean {
    const isPublic = this.reflector.getAllAndOverride<boolean>(IS_PUBLIC_KEY, [
      context.getHandler(),
      context.getClass(),
    ]);
    if (isPublic) return true;

    const metadataValues = this.reflector.getAllAndOverride<
      (UserRole | AccountType)[]
    >(ROLES_GUARD_KEY, [context.getHandler(), context.getClass()]);

    if (!metadataValues || metadataValues.length === 0) return true;

    // Phân loại đúng vai trò + account type
    const roles = metadataValues.filter((v) =>
      Object.values(UserRole).includes(v as UserRole),
    ) as UserRole[];

    const accountTypes = metadataValues.filter((v) =>
      Object.values(AccountType).includes(v as AccountType),
    ) as AccountType[];

    const req = context.switchToHttp().getRequest();
    const user = req.user;

    if (!user) throw new ForbiddenException('Bạn cần đăng nhập');

    // ⭐⭐ GIỮ NGUYÊN 100% LOGIC BẠN ĐANG CHECK ⭐⭐

    // Admin luôn pass
    if (user.role === UserRole.ADMIN) return true;

    const roleAllowed = roles.length === 0 || roles.includes(user.role);
    const accountTypeAllowed =
      accountTypes.length === 0 || accountTypes.includes(user.accountType);

    if (roleAllowed && accountTypeAllowed) return true;

    throw new ForbiddenException(
      'Tài khoản không có quyền truy cập tính năng này',
    );
  }
}
