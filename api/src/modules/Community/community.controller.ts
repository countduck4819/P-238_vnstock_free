import {
  Body,
  Controller,
  Delete,
  Get,
  Inject,
  Param,
  ParseIntPipe,
  Post,
  Query,
  UsePipes,
  ValidationPipe,
} from '@nestjs/common';
import { ApiBearerAuth, ApiTags } from '@nestjs/swagger';
import { CommunityService } from './community.service';
import { CommunityMessagesService } from './community-messages.service';
import {
  CommunityMessagesServiceToken,
  CommunityServiceToken,
} from 'src/shared';
import { Public } from 'src/shared/decorator/is-public.decorator';
import { CurrentUser } from 'src/shared/decorator/current-user.decorator';
import type { AuthUser } from 'src/shared/decorator/current-user.decorator';
import {
  CreateCommunityCommentDto,
  CreateCommunityPostDto,
  GetCommunityPostsQueryDto,
  GetMessagesQueryDto,
  SearchMembersQueryDto,
  SendMessageDto,
  StartConversationDto,
} from './community.dto';

// `whitelist` drops any client-supplied identity fields (userId, authorName…)
// that older clients may still send: identity comes from the access token.
const communityValidation = new ValidationPipe({
  transform: true,
  whitelist: true,
});

@ApiTags('Community')
@ApiBearerAuth()
@UsePipes(communityValidation)
@Controller('/community')
export class CommunityController {
  constructor(
    @Inject(CommunityServiceToken)
    private readonly communityService: CommunityService,
    @Inject(CommunityMessagesServiceToken)
    private readonly messagesService: CommunityMessagesService,
  ) {}

  // ---- Posts ------------------------------------------------------------

  @Public()
  @Get('/posts')
  getPosts(
    @Query() query: GetCommunityPostsQueryDto,
    @CurrentUser() user?: AuthUser,
  ) {
    return this.communityService.getPosts(query, user?.id);
  }

  @Post('/posts')
  createPost(
    @Body() dto: CreateCommunityPostDto,
    @CurrentUser() user: AuthUser,
  ) {
    return this.communityService.createPost(dto, user);
  }

  @Delete('/posts/:id')
  deletePost(
    @Param('id', ParseIntPipe) postId: number,
    @CurrentUser() user: AuthUser,
  ) {
    return this.communityService.deletePost(postId, user);
  }

  @Post('/posts/:id/like')
  toggleLike(
    @Param('id', ParseIntPipe) postId: number,
    @CurrentUser() user: AuthUser,
  ) {
    return this.communityService.toggleLike(postId, user.id);
  }

  @Post('/posts/:id/save')
  toggleSave(
    @Param('id', ParseIntPipe) postId: number,
    @CurrentUser() user: AuthUser,
  ) {
    return this.communityService.toggleSave(postId, user.id);
  }

  @Post('/posts/:id/comments')
  addComment(
    @Param('id', ParseIntPipe) postId: number,
    @Body() dto: CreateCommunityCommentDto,
    @CurrentUser() user: AuthUser,
  ) {
    return this.communityService.addComment(postId, dto, user);
  }

  @Delete('/comments/:id')
  deleteComment(
    @Param('id', ParseIntPipe) commentId: number,
    @CurrentUser() user: AuthUser,
  ) {
    return this.communityService.deleteComment(commentId, user);
  }

  // ---- Members ----------------------------------------------------------

  @Get('/members')
  searchMembers(
    @Query() query: SearchMembersQueryDto,
    @CurrentUser() user: AuthUser,
  ) {
    return this.messagesService.searchMembers(user.id, query.keyword);
  }

  @Public()
  @Get('/members/:id')
  getMember(@Param('id', ParseIntPipe) memberId: number) {
    return this.messagesService.getMember(memberId);
  }

  // ---- Direct messages --------------------------------------------------

  @Get('/conversations')
  listConversations(@CurrentUser() user: AuthUser) {
    return this.messagesService.listConversations(user.id);
  }

  @Post('/conversations')
  startConversation(
    @Body() dto: StartConversationDto,
    @CurrentUser() user: AuthUser,
  ) {
    return this.messagesService.startConversation(user.id, dto.recipientId);
  }

  @Get('/conversations/:id/messages')
  getMessages(
    @Param('id', ParseIntPipe) conversationId: number,
    @Query() query: GetMessagesQueryDto,
    @CurrentUser() user: AuthUser,
  ) {
    return this.messagesService.getMessages(user.id, conversationId, query);
  }

  @Post('/conversations/:id/messages')
  sendMessage(
    @Param('id', ParseIntPipe) conversationId: number,
    @Body() dto: SendMessageDto,
    @CurrentUser() user: AuthUser,
  ) {
    return this.messagesService.sendMessage(
      user.id,
      conversationId,
      dto.content,
    );
  }

  @Post('/conversations/:id/read')
  markRead(
    @Param('id', ParseIntPipe) conversationId: number,
    @CurrentUser() user: AuthUser,
  ) {
    return this.messagesService.markRead(user.id, conversationId);
  }
}
