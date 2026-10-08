import { ApiProperty, ApiPropertyOptional } from "@nestjs/swagger";
import {
  IsArray,
  IsEmail,
  IsEnum,
  IsNotEmpty,
  IsOptional,
  IsString,
  Matches,
  MinLength,
} from "class-validator";
import { AccountType, Gender, UserReqI, UserRole } from "src/shared";

export class UserDTO implements UserReqI {
  @ApiProperty({ example: "user1", type: String })
  @IsString()
  @IsNotEmpty({ message: "Username không được để trống" })
  username: string;

  @ApiProperty({ example: "user1@gmail.com", type: String })
  @IsEmail({}, { message: "Email không hợp lệ" })
  email: string;

  @ApiPropertyOptional({ example: "123 Đường ABC, Hà Nội", type: String })
  @IsOptional()
  @IsString()
  address?: string;

  @ApiProperty({ example: "123456", type: String })
  @IsString()
  @IsNotEmpty({ message: "Mật khẩu không được để trống" })
  @MinLength(6, { message: "Mật khẩu phải có ít nhất 8 ký tự" })
  @Matches(/(?=.*[0-9])/, { message: "Mật khẩu phải chứa ít nhất một số" })
  password: string;

  @ApiPropertyOptional({
    name: "fullName",
    example: "Trần Ngọc Quỳnh",
    type: String,
  })
  @IsOptional()
  @IsString()
  fullName?: string;

  @ApiPropertyOptional({ enum: UserRole, example: UserRole.USER })
  @IsOptional()
  @IsEnum(UserRole, { message: "Vai trò không hợp lệ" })
  role?: UserRole;

  @ApiPropertyOptional({
    name: "accountType",
    enum: AccountType,
    example: AccountType.FREE,
  })
  @IsOptional()
  @IsEnum(AccountType, { message: "Kiểu tài khoản không hợp lệ" })
  accountType?: AccountType;

  @ApiPropertyOptional({
    example: "https://example.com/avatar.jpg",
    type: String,
  })
  @IsOptional()
  @IsString()
  avatar?: string;

  @ApiPropertyOptional({ enum: Gender, example: Gender.FEMALE })
  @IsOptional()
  @IsEnum(Gender, { message: "Giới tính không hợp lệ" })
  gender?: Gender;

  @ApiPropertyOptional({
    name: "citizenId",
    example: "012345678901",
    type: String,
  })
  @IsOptional()
  @IsString()
  citizenId?: string;

  @ApiPropertyOptional({
    name: "watchList",
    example: ["AAA", "VNM", "FPT"],
    type: [String],
  })
  @IsArray()
  @IsOptional()
  @IsString({ each: true })
  watchList: string[];
}
