import { Module } from '@nestjs/common';
import { DatabaseModule } from 'src/database/database.module';
import { DataSource, EntityTarget, ObjectLiteral } from 'typeorm';
import {
  CommunityPostEntity,
  CommunityCommentEntity,
  CommunityLikeEntity,
  CommunitySaveEntity,
  CommunityConversationEntity,
  CommunityMessageEntity,
} from './community.entities';
import { CommunityController } from './community.controller';
import { CommunityService } from './community.service';
import { CommunityMessagesService } from './community-messages.service';
import { CommunityRealtimeService } from './community-realtime.service';
import { CommunityGateway } from './community.gateway';
import { AuthModule } from '../Auth/auth.module';
import { UserModule } from '../Users/users.module';
import {
  DATA_SOURCE,
  CommunityPostRepository,
  CommunityCommentRepository,
  CommunityLikeRepository,
  CommunitySaveRepository,
  CommunityConversationRepository,
  CommunityMessageRepository,
  CommunityServiceToken,
  CommunityMessagesServiceToken,
} from 'src/shared';

const repository = (token: symbol, entity: EntityTarget<ObjectLiteral>) => ({
  provide: token,
  useFactory: (dataSource: DataSource) => dataSource.getRepository(entity),
  inject: [DATA_SOURCE],
});

@Module({
  imports: [DatabaseModule, AuthModule, UserModule],
  controllers: [CommunityController],
  providers: [
    repository(CommunityPostRepository, CommunityPostEntity),
    repository(CommunityCommentRepository, CommunityCommentEntity),
    repository(CommunityLikeRepository, CommunityLikeEntity),
    repository(CommunitySaveRepository, CommunitySaveEntity),
    repository(CommunityConversationRepository, CommunityConversationEntity),
    repository(CommunityMessageRepository, CommunityMessageEntity),
    CommunityRealtimeService,
    CommunityGateway,
    { provide: CommunityServiceToken, useClass: CommunityService },
    {
      provide: CommunityMessagesServiceToken,
      useClass: CommunityMessagesService,
    },
  ],
  exports: [CommunityServiceToken, CommunityMessagesServiceToken],
})
export class CommunityModule {}
