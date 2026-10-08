import {
  BadRequestException,
  Controller,
  Get,
  Param,
  Query,
  UseGuards,
} from '@nestjs/common';
import { ApiBearerAuth } from '@nestjs/swagger';
import { AccountType, HttpStatusCode, ResponseCode } from 'src/shared';
import { Roles } from 'src/shared/decorator/roles.decorator';
import { WaveV6PremiumGuard } from './wave-v6.premium.guard';
import { WaveV6Service } from './wave-v6.service';

@ApiBearerAuth()
@Controller('/wave-v6')
@Roles(AccountType.PREMIUM)
@UseGuards(WaveV6PremiumGuard)
export class WaveV6Controller {
  constructor(private readonly waveV6Service: WaveV6Service) {}

  @Get('/latest')
  async latest(@Query('limit') rawLimit?: string) {
    const limit = this.parseLimit(rawLimit);
    return {
      status: HttpStatusCode.OK,
      code: ResponseCode.SUCCESS,
      message: 'Long-term trend advisory loaded successfully.',
      data: await this.waveV6Service.latest(limit),
    };
  }

  @Get('/:symbol')
  async bySymbol(@Param('symbol') rawSymbol: string) {
    const symbol = rawSymbol.trim().toUpperCase();
    if (!/^[A-Z0-9]{1,10}$/.test(symbol)) {
      throw new BadRequestException('symbol must contain 1-10 letters or digits.');
    }
    return {
      status: HttpStatusCode.OK,
      code: ResponseCode.SUCCESS,
      message: 'Long-term trend advisory loaded successfully.',
      data: await this.waveV6Service.bySymbol(symbol),
    };
  }

  private parseLimit(rawLimit?: string): number {
    if (rawLimit === undefined) return 10;
    const limit = Number(rawLimit);
    if (!Number.isInteger(limit) || limit < 1 || limit > 50) {
      throw new BadRequestException('limit must be an integer between 1 and 50.');
    }
    return limit;
  }
}
