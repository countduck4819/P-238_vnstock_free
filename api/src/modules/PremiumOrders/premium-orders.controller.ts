import {
  Body,
  Controller,
  Delete,
  Get,
  Inject,
  Logger,
  Param,
  Post,
  Put,
  Query,
  Req,
} from '@nestjs/common';
import { ApiBearerAuth } from '@nestjs/swagger';
import { Roles } from 'src/shared/decorator/roles.decorator';
import { Public } from 'src/shared/decorator/is-public.decorator';
import { PremiumOrdersServiceToken, UserRole } from 'src/shared';

import {
  CreatePremiumOrderDto,
  UpdatePremiumOrderStatusDto,
} from './premium-orders.dto';
import { PremiumOrdersService } from './premium-orders.service';

@ApiBearerAuth()
@Controller('/premium-orders')
export class PremiumOrdersController {
  private readonly logger = new Logger(PremiumOrdersService.name);
  constructor(
    @Inject(PremiumOrdersServiceToken)
    protected readonly service: PremiumOrdersService,
  ) {}

  /** Danh sách */
  @Get()
  @Roles(UserRole.ADMIN)
  getAll(@Query() query: Record<string, any>) {
    return this.service.findPaginated(query);
  }

  /** Chi tiết */
  @Get(':id')
  @Roles(UserRole.ADMIN)
  get(@Param('id') id: number) {
    return this.service.findOne(id);
  }

  /** Tạo order + trả link thanh toán PayOS */
  @Post()
  @Roles(UserRole.USER)
  create(@Body() dto: CreatePremiumOrderDto, @Req() req: any) {
    return this.service.createPremiumOrder({
      ...dto,
      userId: req.user.id,
    });
  }

  /** Webhook */
  @Post('/webhook')
  @Public()
  async webhook(@Body() body: any) {
    this.logger.log(
      `Webhook endpoint hit: orderCode=${body?.data?.orderCode ?? 'unknown'}`,
    );

    try {
      const result = await this.service.handleWebhook(body);
      this.logger.log('Webhook result:', result);
      return result;
    } catch (error) {
      this.logger.error('Webhook controller error:', error);
      return { ok: false, error: error.message };
    }
  }

  @Put(':id')
  @Roles(UserRole.ADMIN)
  update(@Param('id') id: number, @Body() dto: UpdatePremiumOrderStatusDto) {
    return this.service.updatePremiumOrder(id, dto);
  }

  @Delete(':id')
  @Roles(UserRole.ADMIN)
  delete(@Param('id') id: number) {
    return this.service.deletePremiumOrder(id);
  }
}
