import { Module } from '@nestjs/common';
import { DatabaseModule } from 'src/database/database.module';
import { DataSource } from 'typeorm';
import {
  DATA_SOURCE,
  StockRecommendationRepository,
  StockRecommendationServiceToken,
  StocksRepository,

} from 'src/shared';
import { StockRecommendationEntity } from './stock-recommendations.entities';
import { StockEntity } from '../Stocks/stocks.entities';
import { StockRecommendationsService } from './stock-recommendations.service';
import { StockRecommendationsController } from './stock-recommendations.controller';


@Module({
  imports: [DatabaseModule],
  controllers: [StockRecommendationsController],
  providers: [
    {
      provide: StockRecommendationRepository,
      useFactory: (dataSource: DataSource) =>
        dataSource.getRepository(StockRecommendationEntity),
      inject: [DATA_SOURCE],
    },
    {
      provide: StocksRepository,
      useFactory: (dataSource: DataSource) =>
        dataSource.getRepository(StockEntity),
      inject: [DATA_SOURCE],
    },
    {
      provide: StockRecommendationServiceToken,
      useClass: StockRecommendationsService,
    },
  ],
  exports: [StockRecommendationRepository, StockRecommendationServiceToken],
})
export class StockRecommendationsModule {}
