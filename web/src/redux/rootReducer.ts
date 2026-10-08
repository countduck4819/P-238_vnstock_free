import stockSymbolsReducer from "@/store/stock-symbols/stock-symbols.reducer";
import usersReducer from "@/store/users/user.reducer";
import financeIndexReducer from "@/store/finance-index/finance-index.reducer";
import industriesReducer from "@/store/industries/industries.reducer";
import stocksReducer from "@/store/stocks/stocks.reducer";
import newsReducer from "@/store/news/news.reducer";
import stockRecommendationsReducer from "@/store/stock-recommendations/stock-recommendations.reducer";
import aiChatReducer from "@/store/ai-chat/aiChat.reducer";
import stockPredictionReducer from "@/store/stock-prediction/stock-prediction.reducer";
import premiumOrdersReducer from "@/store/premium-orders/premium-orders.reducer";
import communityReducer from "@/store/community/community.reducer";
import { combineReducers } from "@reduxjs/toolkit";

export const rootReducer = combineReducers({
    usersReducer: usersReducer,
    stockSymbols: stockSymbolsReducer,
    financeIndex: financeIndexReducer,
    industries: industriesReducer,
    stocks: stocksReducer,
    news: newsReducer,
    stockRecommendations: stockRecommendationsReducer,
    aiChat: aiChatReducer,
    stockPrediction: stockPredictionReducer,
    premiumOrders: premiumOrdersReducer,
    community: communityReducer,
});
