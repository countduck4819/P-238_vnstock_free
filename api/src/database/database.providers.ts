import { AiStockHistoryEntity } from 'src/modules/AiStock/entities/ai-stock-history.entity';
import { IndustryEntity } from 'src/modules/Industries/industries.entities';
import { NewsEntity } from 'src/modules/News/news.entities';
import { PremiumOrderEntity } from 'src/modules/PremiumOrders/premium-orders.entities';
import { StockPredictionEntity } from 'src/modules/StockPrediction/stock-prediction.entities';
import { StockRecommendationEntity } from 'src/modules/StockRecommendation/stock-recommendations.entities';
import { StockEntity } from 'src/modules/Stocks/stocks.entities';
import { UsersEntities } from 'src/modules/Users/users.entities';
import {
  CommunityPostEntity,
  CommunityCommentEntity,
  CommunityLikeEntity,
  CommunitySaveEntity,
} from 'src/modules/Community/community.entities';
import { DATA_SOURCE } from 'src/shared/const';
import { DataSource } from 'typeorm';

export const databaseProviders = [
  {
    provide: DATA_SOURCE,
    useFactory: async () => {
      const dataSource = new DataSource({
        type: 'postgres',
        host: process.env.PGHOST,
        port: Number(process.env.PGPORT),
        username: process.env.POSTGRES_USER,
        password: process.env.POSTGRES_PASSWORD,
        database: process.env.POSTGRES_DB,
        entities: [
          UsersEntities,
          IndustryEntity,
          StockEntity,
          NewsEntity,
          StockRecommendationEntity,
          AiStockHistoryEntity,
          StockPredictionEntity,
          PremiumOrderEntity,
          CommunityPostEntity,
          CommunityCommentEntity,
          CommunityLikeEntity,
          CommunitySaveEntity,
        ],
        synchronize: true,
        logging: true,
      });

      return dataSource.initialize();
    },
  },
];
