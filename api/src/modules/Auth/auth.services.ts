import {
  AuthServiceI,
  HttpStatusCode,
  ResponseCode,
  UserRole,
  UsersRepository,
} from "src/shared";
import { BaseServices } from "../Base/base.services";
import { UsersEntities } from "../Users/users.entities";
import {
  BadRequestException,
  Inject,
  Injectable,
  NotFoundException,
  UnauthorizedException,
} from "@nestjs/common";
import { JwtService } from "@nestjs/jwt";
import { Repository } from "typeorm";
import { LoginDTO } from "./auth.dto";
import * as bcrypt from "bcrypt";
import { filterObjectColumnPublic } from "src/shared/common/util";

@Injectable()
export class AuthService
  extends BaseServices<UsersEntities>
  implements AuthServiceI
{
  protected privateColumns: string[] = ["password"];
  constructor(
    @Inject(UsersRepository)
    protected userRepository: Repository<UsersEntities>,
    protected jwtService: JwtService,
  ) {
    super(userRepository);
  }

  async loginWithPassword(userLogin: LoginDTO): Promise<any> {
    try {
      let user = await this.userRepository.findOne({
        where: { email: userLogin.email },
      });

      if (!user || user?.password === "")
        throw new UnauthorizedException("Email hoặc mật khẩu không đúng");

      const isMatch = await bcrypt.compare(userLogin.password, user.password);
      if (!isMatch)
        throw new UnauthorizedException("Email hoặc mật khẩu không đúng");

      const payload = {
        sub: user.id,
        email: user.email,
        role: user.role,
        accountType: user.accountType,
      };
      const accessToken = await this.jwtService.signAsync(payload, {
        expiresIn: "15m",
      });
      const refreshToken = await this.jwtService.signAsync(payload, {
        expiresIn: "7d",
      });

      const hashedRefreshToken = await bcrypt.hash(refreshToken, 10);
      await this.userRepository.update(user.id, {
        refreshToken: hashedRefreshToken,
      });

      if (user && Object.keys(user).length > 0) {
        user = filterObjectColumnPublic(
          this.getPublishPropertyNameColumn(),
          user,
        ) as any;
      }
      return {
        status: HttpStatusCode.OK,
        code: ResponseCode.SUCCESS,
        message: "Đăng nhập thành công",
        data: {
          user,
          tokens: {
            accessToken,
            refreshToken,
          },
        },
      };
    } catch (e) {
      return {
        status: HttpStatusCode.UNAUTHORIZED,
        code: ResponseCode.ERROR,
        message: "Đăng nhập thất bại",
        data: null,
      };
    }
  }

  async refreshToken(tokenData) {
    const { refreshToken } = tokenData;
    try {
      const payload = await this.jwtService.verifyAsync(refreshToken, {
        secret: process.env.JWT_SECRET || "countduck4819",
      });

      const user = await this.userRepository
        .createQueryBuilder("user")
        .addSelect("user.refreshToken")
        .where("user.id = :id", { id: payload.sub })
        .getOne();

      if (!user || !user.refreshToken) throw new UnauthorizedException();

      const isMatch = await bcrypt.compare(refreshToken, user.refreshToken);

      if (!isMatch) throw new UnauthorizedException();
      const newAccessToken = await this.jwtService.signAsync(
        {
          sub: user.id,
          email: user.email,
          role: user.role,
          accountType: payload.accountType,
        },
        { expiresIn: "15m" },
      );

      // const newRefreshToken = this.jwtService.sign(
      //   { sub: user.id },
      //   { expiresIn: '7d' },
      // );
      // await this.userRepository.update(user.id, {
      //   refreshToken: await bcrypt.hash(newRefreshToken, 10),
      // });
      return {
        status: HttpStatusCode.OK,
        code: ResponseCode.SUCCESS,
        message: "Làm mới token thành công",
        data: {
          user,
          tokens: {
            accessToken: newAccessToken,
            // refreshToken: newRefreshToken,
          },
        },
      };
    } catch (error: any) {
      let message = "Refresh token không hợp lệ hoặc đã bị thu hồi";

      if (error.name === "TokenExpiredError") {
        const payload = this.jwtService.decode(refreshToken);
        if (payload?.sub) {
          await this.userRepository.update(payload.sub, { refreshToken: null });
        }
        message = "Refresh token đã hết hạn, vui lòng đăng nhập lại";
      }

      return {
        status: HttpStatusCode.UNAUTHORIZED,
        code: ResponseCode.ERROR,
        message,
        data: null,
      };
    }
  }

  async logout(userId: number) {
    try {
      if (!userId) {
        throw new BadRequestException("Thiếu userId từ token");
      }

      const user = await this.userRepository.findOneBy({ id: userId });

      if (!user) {
        throw new NotFoundException("Không tìm thấy người dùng");
      }

      await this.userRepository.update(userId, { refreshToken: null });

      return {
        status: HttpStatusCode.OK,
        code: ResponseCode.SUCCESS,
        message: "Đăng xuất thành công",
      };
    } catch (error) {
      return {
        status: HttpStatusCode.INTERNAL_ERROR,
        code: ResponseCode.ERROR,
        message: "Đăng xuất thất bại",
        data: null,
      };
    }
  }

  async socialLogin(profile: any) {
    const { email, name, avatar } = profile;

    let user = await this.userRepository.findOne({ where: { email } });

    if (!user) {
      user = await this.userRepository.save({
        email,
        fullName: name,
        username: email,
        avatar,
        password: "", // không dùng password
        address: "",
      });
    }

    const payload = {
      sub: user.id,
      email: user.email,
      role: user.role,
      accountType: user.accountType,
    };

    const accessToken = await this.jwtService.signAsync(payload, {
      expiresIn: "15m",
    });

    const refreshToken = await this.jwtService.signAsync(payload, {
      expiresIn: "7d",
    });

    await this.userRepository.update(user.id, {
      refreshToken: await bcrypt.hash(refreshToken, 10),
    });

    return {
      status: 200,
      code: "SUCCESS",
      message: "Đăng nhập Google thành công",
      data: {
        user,
        tokens: { accessToken, refreshToken },
      },
    };
  }

  getGoogleAuthUrl() {
    const rootUrl = "https://accounts.google.com/o/oauth2/v2/auth";
    const options = {
      redirect_uri: "http://localhost:3000/auth/google/callback",
      client_id: process.env.GOOGLE_CLIENT_ID as string,
      access_type: "offline",
      response_type: "code",
      prompt: "consent",
      scope:
        "https://www.googleapis.com/auth/userinfo.profile https://www.googleapis.com/auth/userinfo.email",
    };

    return `${rootUrl}?${new URLSearchParams(options).toString()}`;
  }

  async getUserFromToken(token: string) {
    try {
      if (!token || !token.startsWith("Bearer ")) {
        return {
          status: HttpStatusCode.UNAUTHORIZED,
          code: ResponseCode.ERROR,
          message: "Token không hợp lệ",
          data: null,
        };
      }

      const accessToken = token.split(" ")[1];
      const payload = this.jwtService.verify(accessToken);

      const user = await this.repository.findOne({
        where: { id: payload.sub, active: true },
      });

      if (!user) {
        return {
          status: HttpStatusCode.UNAUTHORIZED,
          code: ResponseCode.ERROR,
          message: "User không tồn tại",
          data: null,
        };
      }

      const publicUser = filterObjectColumnPublic(
        this.getPublishPropertyNameColumn(),
        user,
      );

      return {
        status: HttpStatusCode.OK,
        code: ResponseCode.SUCCESS,
        message: "Lấy user thành công!",
        data: [publicUser],
      };
    } catch (err) {
      return {
        status: HttpStatusCode.UNAUTHORIZED,
        code: ResponseCode.ERROR,
        message: "Token không hợp lệ hoặc hết hạn",
        data: null,
      };
    }
  }
}
