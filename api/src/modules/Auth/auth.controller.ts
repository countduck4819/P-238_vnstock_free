import {
  Body,
  Controller,
  Get,
  HttpCode,
  HttpStatus,
  Inject,
  Post,
  Req,
  Res,
  UseGuards,
} from "@nestjs/common";
import { AuthServiceToken, UserRole } from "src/shared";
import { AuthService } from "./auth.services";
import { LoginDTO } from "./auth.dto";
import { Roles } from "src/shared/decorator/roles.decorator";
import { Public } from "src/shared/decorator/is-public.decorator";
import { AuthGuard } from "@nestjs/passport";
import { ApiBearerAuth, ApiBody } from "@nestjs/swagger";
import type { FastifyRequest } from "fastify";
import { GoogleAuthGuard } from "src/shared/guard/google-guard.guard";

@ApiBearerAuth()
@Controller("/auth")
@Roles(UserRole.USER)
export class AuthController {
  constructor(
    @Inject(AuthServiceToken)
    private readonly authService: AuthService,
  ) {}

  @Public()
  @Post("/login")
  async login(
    @Body() dto: LoginDTO,
    // @Res({ passthrough: true }) reply: FastifyReply,
  ) {
    const result = await this.authService.loginWithPassword(dto);

    // if (result.status !== 200) return result;

    // reply.setCookie('accessToken', result.data.tokens.accessToken, {
    //   httpOnly: true,
    //   path: '/',
    //   maxAge: 900,
    //   secure: false,
    //   sameSite: 'lax',
    // });

    return result;
  }

  @HttpCode(HttpStatus.OK)
  @Post("/refresh-token")
  @Public()
  @ApiBody({
    schema: {
      type: "object",
      required: ["refreshToken"],
      properties: { refreshToken: { type: "string" } },
    },
  })
  refreshToken(@Body() tokenData: { refreshToken: string }) {
    return this.authService.refreshToken(tokenData);
  }

  @Post("logout")
  @ApiBearerAuth()
  logout(@Req() req) {
    const userId = req.user?.id;
    return this.authService.logout(userId);
  }

  @Get("google")
  @Public()
  @UseGuards(GoogleAuthGuard)
  async googleLogin() {
    return { msg: "Redirecting to Google..." };
  }

  @Get("google/callback")
  @Public()
  @UseGuards(GoogleAuthGuard)
  async googleCallback(@Req() req, @Res() res) {
    const loginResult = await this.authService.socialLogin(req.user);

    // Set cookie (giống login bằng password)
    res.cookie("accessToken", loginResult.data.tokens.accessToken, {
      httpOnly: false,
      path: "/",
      sameSite: "lax",
    });

    res.cookie("refreshToken", loginResult.data.tokens.refreshToken, {
      httpOnly: false,
      path: "/",
      sameSite: "lax",
    });
    const redirectUrl = process.env.DOMAIN_WEB || "http://localhost:3000";

    res.status(302);
    res.header("Location", redirectUrl);
    res.send();
  }

  // auth.controller.ts - GIỮ NGUYÊN
  // @Get('google')
  // @Public()
  // @UseGuards(GoogleAuthGuard)
  // async googleLogin() {
  //   // Passport tự redirect
  // }

  // @Get('google/callback')
  // @Public()
  // @UseGuards(GoogleAuthGuard)
  // async googleCallback(@Req() req, @Res() res) {
  //   const loginResult = await this.authService.socialLogin(req.user);

  //   res.cookie('accessToken', loginResult.data.tokens.accessToken, {
  //     httpOnly: false,
  //     path: '/',
  //     sameSite: 'lax',
  //   });

  //   res.cookie('refreshToken', loginResult.data.tokens.refreshToken, {
  //     httpOnly: false,
  //     path: '/',
  //     sameSite: 'lax',
  //   });

  //   return res.redirect(process.env.DOMAIN_WEB || 'http://localhost:7000');
  // }

  // --- FACEBOOK AUTH ---
  @Get("facebook")
  @Public()
  @UseGuards(AuthGuard("facebook"))
  async facebookLogin() {
    // Passport sẽ tự redirect tới Facebook
  }

  @Get("facebook/callback")
  @Public()
  @UseGuards(AuthGuard("facebook"))
  async facebookCallback(@Req() req) {
    return this.authService.socialLogin(req.user);
  }

  @Get("me")
  async me(@Req() req: FastifyRequest) {
    const accessToken = req.headers["authorization"] as string;
    return this.authService.getUserFromToken(`${accessToken}`);
  }
}
