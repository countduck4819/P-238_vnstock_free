export enum RoleGuard {
  USER = 'user',
  ADMIN = 'admin',
  FREE = 'free',
  PREMIUM = 'premium',
}
export enum UserRole {
  USER = 'user',
  ADMIN = 'admin',
}

export enum AccountType {
  FREE = 'free',
  PREMIUM = 'premium',
}

export enum Gender {
  MALE = 'male',
  FEMALE = 'female',
  OTHER = 'other',
}

// code response
export enum ResponseCode {
  ERROR = 0,
  SUCCESS = 1,
}

// HTTP status
export enum HttpStatusCode {
  OK = 200,
  CREATED = 201,
  BAD_REQUEST = 400,
  UNAUTHORIZED = 401,
  FORBIDDEN = 403,
  NOT_FOUND = 404,
  INTERNAL_ERROR = 500,
}

export enum StockRecommendationStatus {
  ACTIVE = 'ACTIVE',
  TARGET_HIT = 'TARGET_HIT',
  STOP_LOSS = 'STOP_LOSS',
  CLOSED = 'CLOSED',
}

export enum PremiumOrderStatus {
  PENDING = 'PENDING',
  PAID = 'PAID',
  CANCEL = 'CANCEL',
}
