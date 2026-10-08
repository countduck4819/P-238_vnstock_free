import { Module } from '@nestjs/common';
import { DatabaseModule } from 'src/database/database.module';
import { DataSource, Repository } from 'typeorm';
import { NewsEntity } from './news.entities';
import { NewsController } from './news.controller';

import { DATA_SOURCE, NewsRepository, NewsServiceToken } from 'src/shared';
import { NewsService } from './news.service';

@Module({
  imports: [DatabaseModule],
  controllers: [NewsController],
  providers: [
    {
      provide: NewsRepository,
      useFactory: (dataSource: DataSource): Repository<NewsEntity> =>
        dataSource.getRepository(NewsEntity),
      inject: [DATA_SOURCE],
    },
    {
      provide: NewsServiceToken,
      useClass: NewsService,
    },
  ],
  exports: [NewsRepository, NewsServiceToken],
})
export class NewsModule {}
