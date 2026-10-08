import { Module } from "@nestjs/common";
import { DatabaseModule } from "src/database/database.module";
import { AuthController } from "./auth.controller";
import { UserModule } from "../Users/users.module";
import {
  AuthServiceToken,
  JwtAuthGuardToken,
  JwtStrategyToken,
} from "src/shared";
import { AuthService } from "./auth.services";
import { JwtModule } from "@nestjs/jwt";
import { PassportModule } from "@nestjs/passport";
import { JwtStrategy } from "./jwt.strategy";
import { JwtAuthGuard } from "./jwt-auth.guard";
import { GoogleStrategy } from "./google.strategy";
import { GoogleAuthGuard } from "src/shared/guard/google-guard.guard";
// import { FacebookStrategy } from './facebook.strategy';

@Module({
  imports: [
    DatabaseModule,
    UserModule,
    // PassportModule,
    PassportModule.register({ session: false }),
    JwtModule.register({
      secret: process.env.JWT_SECRET || "countduck4819",
      signOptions: { expiresIn: "1h" },
    }),
  ],
  controllers: [AuthController],
  providers: [
    {
      provide: AuthServiceToken,
      useClass: AuthService,
    },
    {
      provide: JwtStrategyToken,
      useClass: JwtStrategy,
    },
    {
      provide: JwtAuthGuardToken,
      useClass: JwtAuthGuard,
    },
    // FacebookStrategy,
    GoogleStrategy,
    GoogleAuthGuard,
  ],
  exports: [JwtStrategyToken, JwtAuthGuardToken, AuthServiceToken],
})
export class AuthModule {}
