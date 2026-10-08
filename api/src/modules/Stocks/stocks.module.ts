import { Module } from '@nestjs/common';
import { DatabaseModule } from 'src/database/database.module';
import { StockController } from './stocks.controller';
import { DATA_SOURCE, StocksRepository, StocksServiceToken } from 'src/shared';
import { DataSource } from 'typeorm';
import { StockEntity } from './stocks.entities';
import { StockService } from './stocks.service';

@Module({
  imports: [DatabaseModule],
  controllers: [StockController],
  providers: [
    {
      provide: StocksRepository,
      useFactory: (dataSource: DataSource) =>
        dataSource.getRepository(StockEntity),
      inject: [DATA_SOURCE],
    },
    {
      provide: StocksServiceToken,
      useClass: StockService,
    },
  ],
  exports: [StocksRepository, StocksServiceToken],
})
export class StocksModule {}
