import { Controller, Get, Inject, Param, Post, Query } from '@nestjs/common';
import { AccountType, StockPredictionServiceToken, UserRole } from 'src/shared';
import { StockPredictionService } from './stock-prediction.service';
import { Roles } from 'src/shared/decorator/roles.decorator';
import { Public } from 'src/shared/decorator/is-public.decorator';
import { ApiBearerAuth } from '@nestjs/swagger';

@ApiBearerAuth()
@Controller('/stock-prediction')
@Roles(UserRole.ADMIN)
export class StockPredictionController {
  constructor(
    @Inject(StockPredictionServiceToken)
    private readonly predictService: StockPredictionService,
  ) {}

  @Post('/import')
  async importFromJson() {
    return this.predictService.importFromJson();
  }

  @Get('/latest/:ticker')
  @Public()
  async getLatest(@Param('ticker') ticker: string) {
    return this.predictService.getLatest(ticker.toUpperCase());
  }

  @Get()
  @Roles(AccountType.PREMIUM)
  async getAll(@Query() query: Record<string, any>) {
    return this.predictService.findAll(query);
  }
}
