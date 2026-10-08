import { Module } from '@nestjs/common';
import { DatabaseModule } from 'src/database/database.module';
import {
  DATA_SOURCE,
  StockPredictionRepository,
  StockPredictionServiceToken,
} from 'src/shared';
import { DataSource } from 'typeorm';
import { StockPredictionEntity } from './stock-prediction.entities';
import { StockPredictionService } from './stock-prediction.service';
import { StockPredictionController } from './stock-prediction.controller';

@Module({
  imports: [DatabaseModule],
  controllers: [StockPredictionController],
  providers: [
    {
      provide: StockPredictionRepository,
      useFactory: (dataSource: DataSource) =>
        dataSource.getRepository(StockPredictionEntity),
      inject: [DATA_SOURCE],
    },
    {
      provide: StockPredictionServiceToken,
      useClass: StockPredictionService,
    },
  ],
  exports: [StockPredictionRepository, StockPredictionServiceToken],
})
export class StockPredictionModule {}
