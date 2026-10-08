import { Module } from '@nestjs/common';
import { AppService } from './app.service';
import { UserModule } from './modules/Users/users.module';
import { DatabaseModule } from './database/database.module';
import { AuthModule } from './modules/Auth/auth.module';
import { APP_GUARD } from '@nestjs/core';
import { JwtAuthGuardToken } from './shared';
import { RolesGuard } from './shared/guard/roles-guard.guard';
import { UploadModule } from './modules/UploadFile/upload.module';
import { IndustryModule } from './modules/Industries/industries.module';
import { StocksModule } from './modules/Stocks/stocks.module';
import { NewsModule } from './modules/News/news.module';
import { StockRecommendationsModule } from './modules/StockRecommendation/stock-recommendations.module';
import { ScheduleModule } from '@nestjs/schedule';
import { AiStockModule } from './modules/AiStock/ai-stock.module';
import { StockPredictionModule } from './modules/StockPrediction/stock-prediction.module';
import { PremiumOrdersModule } from './modules/PremiumOrders/premium-orders.module';
import { WaveH120Module } from './modules/WaveH120/wave-h120.module';
import { WaveV6Module } from './modules/WaveV6/wave-v6.module';
import { CommunityModule } from './modules/Community/community.module';
// import { PayOSModule } from './modules/PayOS/payos.module';
@Module({
  imports: [
    DatabaseModule,
    UserModule,
    AuthModule,
    UploadModule,
    IndustryModule,
    StocksModule,
    NewsModule,
    StockRecommendationsModule,
    AiStockModule,
    StockPredictionModule,
    WaveH120Module,
    WaveV6Module,
    CommunityModule,
    ScheduleModule.forRoot(),
    // PayOSModule,
    PremiumOrdersModule,
  ],
  controllers: [],
  providers: [
    AppService,
    { provide: APP_GUARD, useExisting: JwtAuthGuardToken },
    { provide: APP_GUARD, useClass: RolesGuard },
  ],
})
export class AppModule {}
