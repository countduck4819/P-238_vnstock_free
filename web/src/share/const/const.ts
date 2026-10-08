import { StockIndex } from "../enum";

export const publicRouters: string[] = [
    "/login",
    "/register",
    "/privacy-policy",
    "/not-found",
    "/dashboard",
    "/home",
    "/ma-chung-khoan",
    "/tin-tuc",
    "/ve-chung-toi",
    "/landing",
    "/cong-dong",
    "/profile",
    "/settings",
];

export const STOCK_INDEX_MAP: Record<StockIndex, string> = {
    [StockIndex.VNINDEX]: "Chỉ số VNINDEX",
    [StockIndex.HNXINDEX]: "Chỉ số HNXINDEX",
    [StockIndex.UPCOMINDEX]: "Chỉ số UPCOMINDEX",
};
