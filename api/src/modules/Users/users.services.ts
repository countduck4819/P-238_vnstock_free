import {
  BadRequestException,
  Inject,
  Injectable,
  UnauthorizedException,
} from "@nestjs/common";
import { BaseServices } from "../Base/base.services";
import { UsersEntities } from "./users.entities";
import {
  AuthServiceToken,
  HttpStatusCode,
  ResponseCode,
  UsersRepository,
  UsersServiceI,
} from "src/shared";
import { IsNull, Repository } from "typeorm";
import * as bcrypt from "bcrypt";
import { emailRegex, filterObjectColumnPublic } from "src/shared/common/util";

@Injectable()
export class UsersService
  extends BaseServices<UsersEntities>
  implements UsersServiceI {
  protected privateColumns = ["refreshToken", "password"];

  constructor(
    @Inject(UsersRepository)
    repository: Repository<UsersEntities>,
  ) {
    super(repository);
  }

  async create(dataReq: any) {
    try {
      const data: any = [];

      if (!emailRegex.test(dataReq.email)) {
        throw new BadRequestException("Email không hợp lệ");
        // return {
        //   status: HttpStatusCode.BAD_REQUEST,
        //   code: ResponseCode.ERROR,
        //   message: 'Email không hợp lệ',
        //   data: null,
        // };
      }

      if (dataReq.email) {
        const existingUser = await this.repository.findOne({
          where: {
            email: dataReq.email,
            active: true,
            deletedAt: IsNull(),
          },
        });

        if (existingUser) {
          throw new BadRequestException("Email đã tồn tại");
          // return {
          //   status: HttpStatusCode.BAD_REQUEST,
          //   code: ResponseCode.ERROR,
          //   message: 'Email đã tồn tại',
          //   data: null,
          // };
        }
      }

      if (dataReq.password) {
        const saltRounds = 10;
        dataReq.password = await bcrypt.hash(dataReq.password, saltRounds);
      }

      const result = await this.repository
        .createQueryBuilder(this.getTableName())
        .insert()
        .values(dataReq)
        .execute();

      const id = result.identifiers[0]?.id;
      if (!id) throw new Error("Insert failed");

      let object = await this.repository.findOne({ where: { id } });
      if (object && Object.keys(object).length > 0) {
        object = filterObjectColumnPublic(
          this.getPublishPropertyNameColumn(),
          object,
        ) as any;
      }
      data.push(object);
      return {
        status: HttpStatusCode.OK,
        code: ResponseCode.SUCCESS,
        message: `Tạo tài khoản user thành công!`,
        data,
      };
    } catch (e) {
      throw new BadRequestException(e);
      // return {
      //   status: HttpStatusCode.INTERNAL_ERROR,
      //   code: ResponseCode.ERROR,
      //   message: (e as Error).message,
      //   data: null,
      // };
    }
  }

  async updateOne(id: number, dataReq: any) {
    try {
      const data: any = [];
      const newDataReq = this.convertDatabaseNameToProperty(dataReq);

      // Nếu có password gửi lên → hash
      if (newDataReq.password) {
        if (newDataReq.password.trim() === "") {
          // Nếu gửi password rỗng thì bỏ luôn, không update
          delete newDataReq.password;
        } else {
          const saltRounds = 10;
          newDataReq.password = await bcrypt.hash(
            newDataReq.password,
            saltRounds,
          );
        }
      }

      const query = this.repository.createQueryBuilder();
      const updateResult = await query
        .update(this.repository.target)
        .set(newDataReq as any)
        .where("id = :id", { id })
        .andWhere("active = true")
        .execute();

      if (updateResult.affected === 0) {
        throw new Error("Không tìm thấy user hoặc không thể cập nhật");
      }
      const object = await this.repository.findOne({ where: { id } });
      data.push(object);
      return {
        status: HttpStatusCode.OK,
        code: ResponseCode.SUCCESS,
        message: `Cập nhật tài khoản thành công`,
        data,
      };
    } catch (e) {
      return {
        status: HttpStatusCode.INTERNAL_ERROR,
        code: ResponseCode.ERROR,
        message: (e as Error).message,
        data: null,
      };
    }
  }
}
