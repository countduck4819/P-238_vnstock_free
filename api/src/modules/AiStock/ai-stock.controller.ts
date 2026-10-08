import {
  Body,
  Controller,
  Delete,
  Get,
  Inject,
  Param,
  ParseIntPipe,
  Post,
  Put,
  Query,
} from '@nestjs/common';
import { ApiBearerAuth } from '@nestjs/swagger';

import { AiStockService } from './ai-stock.service';
import { AiStockServiceToken, UserRole } from 'src/shared';
import { Roles } from 'src/shared/decorator/roles.decorator';
import { Public } from 'src/shared/decorator/is-public.decorator';
import { AiStockAskDto, AiStockHistoryDto } from './ai-stock.dto';

@ApiBearerAuth()
@Controller('/ai-stock')
@Roles(UserRole.USER)
export class AiStockController {
  constructor(
    @Inject(AiStockServiceToken)
    protected aiStockService: AiStockService,
  ) {}

  // CRUD history dùng BaseServices

  // Lấy danh sách lịch sử
  @Get()
  getAll(@Query() condition: Record<string, any>) {
    return this.aiStockService.find(condition);
  }

  // Lấy chi tiết 1 lịch sử
  @Get(':id')
  get(@Param('id') id: number) {
    return this.aiStockService.findOne(id);
  }

  // Tạo bản ghi history (ít dùng, chủ yếu để debug)
  @Post()
  create(@Body() dto: AiStockHistoryDto) {
    return this.aiStockService.create(dto);
  }

  // Cập nhật history
  @Put(':id')
  update(@Param('id') id: number, @Body() dto: AiStockHistoryDto) {
    return this.aiStockService.updateOne(id, dto);
  }

  // Xóa mềm history
  @Delete(':id')
  remove(@Param('id') id: number) {
    return this.aiStockService.softDelete(id);
  }

  // Endpoint chính: hỏi AI
  @Post('/ask')
  @Public()
  ask(@Body() dto: AiStockAskDto) {
    return this.aiStockService.askStockAi(dto);
  }

  @Get('history/:userId')
  async getHistory(@Param('userId', ParseIntPipe) userId: number) {
    return this.aiStockService.getHistoryByUser(userId);
  }
}
