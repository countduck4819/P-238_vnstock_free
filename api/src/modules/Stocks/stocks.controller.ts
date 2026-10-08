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
import { StockDto } from './stocks.dto';
import { StockService } from './stocks.service';
import { StocksServiceToken, UserRole } from 'src/shared';
import { Roles } from 'src/shared/decorator/roles.decorator';
import { Public } from 'src/shared/decorator/is-public.decorator';
import { ApiBearerAuth } from '@nestjs/swagger';

@ApiBearerAuth()
@Controller('/stocks')
@Roles(UserRole.ADMIN)
export class StockController {
  constructor(
    @Inject(StocksServiceToken)
    protected readonly stockService: StockService,
  ) {}
  // @Get('/vnstock')
  // @Public()
  // getStocks() {
  //   return this.stockService.getDataVnstock();
  // }

  @Get('/listing-stock')
  @Public()
  getDataListingStock() {
    return this.stockService.getListingStock();
  }

  @Get('/stock-symbols')
  @Public()
  getDataStockSymbols() {
    return this.stockService.getStockSymbols();
  }

  @Get('/overview')
  @Public()
  getDataOverview() {
    return this.stockService.getOverview();
  }

  @Get('/candle/:symbol')
  @Public()
  getCandle(@Param('symbol') symbol: string) {
    return this.stockService.getCandleData(symbol);
  }

  // Lấy danh sách hoặc tìm theo điều kiện
  @Get()
  @Public()
  getAll(@Query() query: Record<string, any>) {
    const page = Number(query.page) || 1;
    const limit = Number(query.limit) || 10;

    // query có thể gồm { page, limit, search }
    return this.stockService.paginate(query, page, limit);
  }

  @Public()
  // Lấy chi tiết 1 cổ phiếu theo id
  @Get(':id')
  get(@Param('id') id: number) {
    return this.stockService.findOne(id);
  }

  // Lấy cổ phiếu theo ngành nghề
  @Get('/industry/:industryId')
  @Public()
  getByIndustry(@Param('industryId') industryId: number) {
    return this.stockService.findByIndustry(industryId);
  }

  // Tạo mới cổ phiếu
  @Post()
  create(@Body() dto: StockDto) {
    return this.stockService.create(dto);
  }

  // Cập nhật cổ phiếu theo id
  @Put(':id')
  update(@Param('id') id: number, @Body() dto: StockDto) {
    return this.stockService.updateOne(id, dto);
  }

  // Xóa mềm cổ phiếu
  @Delete(':id')
  remove(@Param('id') id: number) {
    return this.stockService.softDelete(id);
  }
}
