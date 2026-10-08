import { Module } from "@nestjs/common";
import { DatabaseModule } from "src/database/database.module";
import { UsersController } from "./users.controller";
import { DATA_SOURCE, UsersRepository, UsersServiceToken } from "src/shared";

import { UsersEntities } from "./users.entities";
import { UsersService } from "./users.services";
import { DataSource } from "typeorm";
import { AuthModule } from "../Auth/auth.module";

@Module({
  imports: [DatabaseModule],
  controllers: [UsersController],
  providers: [
    {
      provide: UsersRepository,
      useFactory: (dataSource: DataSource) =>
        dataSource.getRepository(UsersEntities),
      inject: [DATA_SOURCE],
    },
    {
      provide: UsersServiceToken,
      useClass: UsersService,
    },
  ],
  exports: [UsersRepository, UsersServiceToken],
})
export class UserModule {}
