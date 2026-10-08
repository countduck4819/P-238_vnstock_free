import { Injectable } from "@nestjs/common";
import { PassportStrategy } from "@nestjs/passport";
import { ExtractJwt, Strategy } from "passport-jwt";
import { AccountType, UserRole } from "src/shared";

@Injectable()
export class JwtStrategy extends PassportStrategy(Strategy) {
  constructor() {
    super({
      jwtFromRequest: ExtractJwt.fromAuthHeaderAsBearerToken(),
      ignoreExpiration: false,
      secretOrKey: process.env.JWT_SECRET || "countduck4819",
    });
  }

  async validate(payload: {
    sub: number;
    email: string;
    role: UserRole;
    accountType: AccountType;
  }) {
    return {
      id: payload.sub,
      email: payload.email,
      role: payload.role,
      accountType: payload.accountType,
    };
  }
}
