import { Module } from '@nestjs/common';
import { DatabaseModule } from 'src/database/database.module';
import {
  DATA_SOURCE,
  IndustryRepository,
  IndustryServiceToken,
} from 'src/shared';
import { DataSource } from 'typeorm';
import { IndustryEntity } from './industries.entities';
import { IndustryService } from './industries.service';
import { IndustryController } from './industries.controller';

@Module({
  imports: [DatabaseModule],
  controllers: [IndustryController],
  providers: [
    {
      provide: IndustryRepository,
      useFactory: (dataSource: DataSource) =>
        dataSource.getRepository(IndustryEntity),
      inject: [DATA_SOURCE],
    },
    {
      provide: IndustryServiceToken,
      useClass: IndustryService,
    },
  ],
  exports: [IndustryRepository, IndustryServiceToken],
})
export class IndustryModule {}
