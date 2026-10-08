import { Module } from '@nestjs/common';
import { WaveV6Controller } from './wave-v6.controller';
import { WaveV6PremiumGuard } from './wave-v6.premium.guard';
import { WaveV6Service } from './wave-v6.service';

@Module({
  controllers: [WaveV6Controller],
  providers: [WaveV6Service, WaveV6PremiumGuard],
})
export class WaveV6Module {}
