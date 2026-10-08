import { ApiProperty } from "@nestjs/swagger";
import {
  IsEmail,
  IsNotEmpty,
  IsString,
  Matches,
  MinLength,
} from "class-validator";

export class LoginDTO {
  @ApiProperty({ example: "user1@gmail.com", type: String })
  @IsEmail({}, { message: "Email không hợp lệ" })
  email: string;

  @ApiProperty({ example: "123456", type: String })
  @IsString()
  @IsNotEmpty({ message: "Mật khẩu không được để trống" })
  @MinLength(6, { message: "Mật khẩu phải có ít nhất 8 ký tự" })
  @Matches(/(?=.*[0-9])/, { message: "Mật khẩu phải chứa ít nhất một số" })
  password: string;
}
