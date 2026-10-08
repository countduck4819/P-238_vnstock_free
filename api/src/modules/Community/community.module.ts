import { Module } from '@nestjs/common';
import { DatabaseModule } from 'src/database/database.module';
import { DataSource, Repository } from 'typeorm';
import {
  CommunityPostEntity,
  CommunityCommentEntity,
  CommunityLikeEntity,
  CommunitySaveEntity,
} from './community.entities';
import { CommunityController } from './community.controller';
import { CommunityService } from './community.service';
import {
  DATA_SOURCE,
  CommunityPostRepository,
  CommunityCommentRepository,
  CommunityLikeRepository,
  CommunitySaveRepository,
  CommunityServiceToken,
} from 'src/shared';

@Module({
  imports: [DatabaseModule],
  controllers: [CommunityController],
  providers: [
    {
      provide: CommunityPostRepository,
      useFactory: (dataSource: DataSource): Repository<CommunityPostEntity> =>
        dataSource.getRepository(CommunityPostEntity),
      inject: [DATA_SOURCE],
    },
    {
      provide: CommunityCommentRepository,
      useFactory: (dataSource: DataSource): Repository<CommunityCommentEntity> =>
        dataSource.getRepository(CommunityCommentEntity),
      inject: [DATA_SOURCE],
    },
    {
      provide: CommunityLikeRepository,
      useFactory: (dataSource: DataSource): Repository<CommunityLikeEntity> =>
        dataSource.getRepository(CommunityLikeEntity),
      inject: [DATA_SOURCE],
    },
    {
      provide: CommunitySaveRepository,
      useFactory: (dataSource: DataSource): Repository<CommunitySaveEntity> =>
        dataSource.getRepository(CommunitySaveEntity),
      inject: [DATA_SOURCE],
    },
    {
      provide: CommunityServiceToken,
      useClass: CommunityService,
    },
  ],
  exports: [
    CommunityPostRepository,
    CommunityCommentRepository,
    CommunityLikeRepository,
    CommunitySaveRepository,
    CommunityServiceToken,
  ],
})
export class CommunityModule {}
