import {
  Body,
  Controller,
  Delete,
  Get,
  Inject,
  Param,
  Post,
  Put,
  Query,
} from '@nestjs/common';
import { ApiBearerAuth } from '@nestjs/swagger';
import { Roles } from 'src/shared/decorator/roles.decorator';
import { Public } from 'src/shared/decorator/is-public.decorator';
import {
  UserRole,
  StockRecommendationServiceToken,
  AccountType,
} from 'src/shared';
import { StockRecommendationsService } from './stock-recommendations.service';
import { StockRecommendationDto } from './stock-recommendations.dto';

@ApiBearerAuth()
@Controller('/stock-recommendations')
@Roles(UserRole.ADMIN)
export class StockRecommendationsController {
  constructor(
    @Inject(StockRecommendationServiceToken)
    protected readonly service: StockRecommendationsService,
  ) {}

  /** 📜 Danh sách phân trang */

  @Get()
  @Roles(UserRole.USER, AccountType.PREMIUM)
  getAll(@Query() query: Record<string, any>) {
    return this.service.findPaginated(query);
  }

  /** 🔍 Chi tiết */
  @Get(':id')
  get(@Param('id') id: number) {
    return this.service.findOne(id);
  }

  /** ➕ Tạo mới */
  @Post()
  create(@Body() dto: StockRecommendationDto) {
    return this.service.create(dto);
  }

  /** ✏️ Cập nhật */
  @Put(':id')
  update(@Param('id') id: number, @Body() dto: StockRecommendationDto) {
    return this.service.updateOne(id, dto);
  }

  /** 🗑️ Xóa mềm */
  @Delete(':id')
  remove(@Param('id') id: number) {
    return this.service.softDelete(id);
  }

  /** 📊 Mã chưa có khuyến nghị ACTIVE */
  @Get('/available/stocks')
  @Public()
  getAvailableStocks() {
    return this.service.getAvailableStocks();
  }
}
