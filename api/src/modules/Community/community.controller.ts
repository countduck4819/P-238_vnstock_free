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
  Req,
} from '@nestjs/common';
import { ApiBearerAuth, ApiTags } from '@nestjs/swagger';
import { CommunityService } from './community.service';
import { CommunityServiceToken } from 'src/shared';
import { Public } from 'src/shared/decorator/is-public.decorator';
import {
  CreateCommunityPostDto,
  CreateCommunityCommentDto,
  GetCommunityPostsQueryDto,
} from './community.dto';

@ApiTags('Community')
@ApiBearerAuth()
@Controller('/community')
export class CommunityController {
  constructor(
    @Inject(CommunityServiceToken)
    private readonly communityService: CommunityService,
  ) {}

  @Public()
  @Get('/posts')
  getPosts(@Query() query: GetCommunityPostsQueryDto, @Req() req: any) {
    const currentUserId = req.user?.id || (query.userId ? Number(query.userId) : undefined);
    return this.communityService.getPosts(query, currentUserId);
  }

  @Public()
  @Post('/posts')
  createPost(@Body() dto: CreateCommunityPostDto, @Req() req: any) {
    const currentUser = req.user || (dto.userId ? {
      id: dto.userId,
      fullName: dto.authorName,
      username: dto.authorName,
      avatar: dto.authorAvatar,
      role: dto.authorBadge === 'Chuyên gia' ? 'Admin' : 'User',
    } : undefined);
    return this.communityService.createPost(dto, currentUser);
  }

  @Public()
  @Post('/posts/:id/like')
  toggleLike(
    @Param('id', ParseIntPipe) postId: number,
    @Body() body: { userId?: number },
    @Req() req: any,
  ) {
    const userId = req.user?.id || body.userId || 1;
    return this.communityService.toggleLike(postId, userId);
  }

  @Public()
  @Post('/posts/:id/save')
  toggleSave(
    @Param('id', ParseIntPipe) postId: number,
    @Body() body: { userId?: number },
    @Req() req: any,
  ) {
    const userId = req.user?.id || body.userId || 1;
    return this.communityService.toggleSave(postId, userId);
  }

  @Public()
  @Post('/posts/:id/comments')
  addComment(
    @Param('id', ParseIntPipe) postId: number,
    @Body() dto: CreateCommunityCommentDto,
    @Req() req: any,
  ) {
    const currentUser = req.user || (dto.userId ? {
      id: dto.userId,
      fullName: dto.authorName,
      username: dto.authorName,
      avatar: dto.authorAvatar,
    } : undefined);
    return this.communityService.addComment(postId, dto, currentUser);
  }

  @Public()
  @Delete('/posts/:id')
  deletePost(
    @Param('id', ParseIntPipe) postId: number,
    @Query() query: { userId?: number; role?: string },
    @Req() req: any,
  ) {
    const currentUser = req.user || (query.userId ? {
      id: Number(query.userId),
      role: query.role,
    } : undefined);
    return this.communityService.deletePost(postId, currentUser);
  }
}
