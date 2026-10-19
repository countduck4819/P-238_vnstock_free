export const DATA_SOURCE = Symbol('DATA_SOURCE');

export const JwtStrategyToken = Symbol('JwtStrategy');
export const JwtAuthGuardToken = Symbol('JwtAuthGuard');

// Users
export const UsersServiceToken = Symbol('UserService');
export const UsersRepository = Symbol('UsersRepository');

// Auth
export const AuthServiceToken = Symbol('AuthService');

// Roles guard
export const RolesGuardToken = Symbol('RolesGuard');

// Upload file
export const UploadToken = Symbol('Upload file');

// Industry
export const IndustryServiceToken = Symbol('IndustryService');
export const IndustryRepository = Symbol('IndustryRepository');

// Stocks
export const StocksServiceToken = Symbol('StocksService');
export const StocksRepository = Symbol('StocksRepository');

// News
export const NewsRepository = Symbol('NewsRepository');
export const NewsServiceToken = Symbol('NewsServiceToken');

// Stock Recommendations
export const StockRecommendationServiceToken = Symbol(
  'StockRecommendationService',
);
export const StockRecommendationRepository = Symbol(
  'StockRecommendationRepository',
);

export const AiStockServiceToken = Symbol('AiStockServiceToken');
export const AiStockRepository = Symbol('AiStockRepository');

export const StockPredictionRepository = Symbol('STOCK_PREDICTION_REPO');
export const StockPredictionServiceToken = Symbol(
  'STOCK_PREDICTION_SERVICE_TOKEN',
);

export const PremiumOrdersRepository = Symbol('PremiumOrdersRepository');
export const PremiumOrdersServiceToken = Symbol('PremiumOrdersService');

// Community Module
export const CommunityPostRepository = Symbol('CommunityPostRepository');
export const CommunityCommentRepository = Symbol('CommunityCommentRepository');
export const CommunityLikeRepository = Symbol('CommunityLikeRepository');
export const CommunitySaveRepository = Symbol('CommunitySaveRepository');
export const CommunityServiceToken = Symbol('CommunityServiceToken');
export const CommunityConversationRepository = Symbol(
  'CommunityConversationRepository',
);
export const CommunityMessageRepository = Symbol('CommunityMessageRepository');
export const CommunityMessagesServiceToken = Symbol(
  'CommunityMessagesServiceToken',
);

// Browser origins allowed to call the API and open the realtime socket.
// Extra origins can be appended with a comma-separated CORS_ORIGINS env var.
export const ALLOWED_ORIGINS: string[] = [
  'http://localhost:3000',
  'http://localhost:8000',
  'http://fireant.io.vn',
  'https://fireant.io.vn',
  'http://c4-app-238.io.vn',
  'https://c4-app-238.io.vn',
  ...(process.env.CORS_ORIGINS ?? '')
    .split(',')
    .map((origin) => origin.trim())
    .filter(Boolean),
];
