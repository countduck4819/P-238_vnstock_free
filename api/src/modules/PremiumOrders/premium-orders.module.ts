import { Module } from '@nestjs/common';
import { DatabaseModule } from 'src/database/database.module';
import { DataSource } from 'typeorm';
import { PremiumOrderEntity } from './premium-orders.entities';
import { PremiumOrdersController } from './premium-orders.controller';
import { PremiumOrdersService } from './premium-orders.service';
import {
  DATA_SOURCE,
  PremiumOrdersRepository,
  PremiumOrdersServiceToken,
  UsersRepository,
} from 'src/shared';
import { UsersEntities } from '../Users/users.entities';
import { UserModule } from '../Users/users.module';

@Module({
  imports: [DatabaseModule, UserModule],
  controllers: [PremiumOrdersController],
  providers: [
    {
      provide: PremiumOrdersRepository,
      useFactory: (ds: DataSource) => ds.getRepository(PremiumOrderEntity),
      inject: [DATA_SOURCE],
    },
    {
      provide: UsersRepository,
      useFactory: (ds: DataSource) => ds.getRepository(UsersEntities),
      inject: [DATA_SOURCE],
    },
    {
      provide: PremiumOrdersServiceToken,
      useClass: PremiumOrdersService,
    },
  ],
  exports: [PremiumOrdersRepository, PremiumOrdersServiceToken],
})
export class PremiumOrdersModule {}
