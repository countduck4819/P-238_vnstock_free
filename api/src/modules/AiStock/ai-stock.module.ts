import { Module } from '@nestjs/common';
import { DatabaseModule } from 'src/database/database.module';
import {
  DATA_SOURCE,
  AiStockRepository,
  AiStockServiceToken,
} from 'src/shared';
import { DataSource } from 'typeorm';

import { AiStockService } from './ai-stock.service';
import { AiStockController } from './ai-stock.controller';
import { HttpModule } from '@nestjs/axios';
import { AiStockHistoryEntity } from './entities/ai-stock-history.entity';
import { StocksModule } from '../Stocks/stocks.module';

@Module({
  imports: [DatabaseModule, HttpModule, StocksModule],
  controllers: [AiStockController],
  providers: [
    {
      provide: AiStockRepository,
      useFactory: (dataSource: DataSource) =>
        dataSource.getRepository(AiStockHistoryEntity),
      inject: [DATA_SOURCE],
    },
    {
      provide: AiStockServiceToken,
      useClass: AiStockService,
    },
  ],
  exports: [AiStockRepository, AiStockServiceToken],
})
export class AiStockModule {}
