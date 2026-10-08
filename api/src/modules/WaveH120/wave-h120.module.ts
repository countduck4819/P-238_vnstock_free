import { Module } from '@nestjs/common';
import { WaveH120Controller } from './wave-h120.controller';
import { WaveH120PremiumGuard } from './wave-h120.premium.guard';
import { WaveH120Service } from './wave-h120.service';

@Module({
  controllers: [WaveH120Controller],
  providers: [WaveH120Service, WaveH120PremiumGuard],
})
export class WaveH120Module {}
