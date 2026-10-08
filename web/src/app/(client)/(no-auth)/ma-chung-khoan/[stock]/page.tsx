"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useAppDispatch, useAppSelector } from "@/redux/hooks";
import { fetchStockCandleData, fetchStocks } from "@/store/stock-symbols/stock-symbols.api";
import TradingViewWidget from "@/share/components/TradingViewWidget";
import StockInfoCard from "@/share/components/StockInfoCard";
import { Clock, Star } from "lucide-react";
import NewsListJson from "@/share/components/NewsListJson";
import NotFound from "@/app/not-found";
import StockDetailLoading from "./loading";
import { StockIndex } from "@/share/enum";

export default function Page() {
    const { stock } = useParams();
    const dispatch = useAppDispatch();
    const { candleData, stocksFullList } = useAppSelector(
        (state) => state.stockSymbols,
    );

    const rawStock = Array.isArray(stock) ? stock[0] : stock;
    const symbol = decodeURIComponent(String(rawStock || "")).trim().toUpperCase();

    const [isInitialLoading, setIsInitialLoading] = useState(
        !stocksFullList || stocksFullList.length === 0,
    );
    const [overviewData, setOverviewData] = useState<{ price: number; change: number } | null>(null);

    useEffect(() => {
        let isMounted = true;
        const loadStocks = async () => {
            if (!stocksFullList || stocksFullList.length === 0) {
                try {
                    await dispatch(fetchStocks()).unwrap();
                } catch {
                    // Ignore error
                }
            }
            if (isMounted) {
                setIsInitialLoading(false);
            }
        };

        loadStocks();

        return () => {
            isMounted = false;
        };
    }, [dispatch, stocksFullList?.length]);

    const stockInfo = useMemo(
        () => stocksFullList?.find((s) => s.symbol.toUpperCase() === symbol),
        [stocksFullList, symbol],
    );

    const isKnownIndex = useMemo(() => {
        const indexValues = Object.values(StockIndex) as string[];
        return (
            indexValues.includes(symbol) ||
            ["VNINDEX", "HNXINDEX", "UPCOMINDEX", "VN30", "VN100"].includes(symbol)
        );
    }, [symbol]);

    const companyDisplayName = useMemo(() => {
        const raw = stockInfo?.org_name || (stockInfo as any)?.organ_name;
        if (raw && raw.trim().toUpperCase() !== symbol) {
            return raw;
        }
        return isKnownIndex ? `Chỉ số ${symbol}` : `Cổ phiếu ${symbol}`;
    }, [stockInfo, symbol, isKnownIndex]);

    const isValidStock = useMemo(() => {
        if (!symbol) return false;
        return Boolean(stockInfo || isKnownIndex);
    }, [symbol, stockInfo, isKnownIndex]);

    useEffect(() => {
        if (!isInitialLoading && isValidStock && symbol) {
            dispatch(fetchStockCandleData(symbol));
            // Fetch live overview for fast, synchronized price matching
            fetch("/api/stocks/overview")
                .then((r) => (r.ok ? r.json() : null))
                .then((json) => {
                    const data = json?.data || json;
                    if (data && data[symbol]) {
                        setOverviewData(data[symbol]);
                    }
                })
                .catch(() => { });
        }
    }, [dispatch, isInitialLoading, isValidStock, symbol]);

    if (isInitialLoading) {
        return <StockDetailLoading />;
    }

    if (!isValidStock) {
        return <NotFound />;
    }

    const latestCandle = candleData[candleData.length - 1];
    const prevCandle = candleData[candleData.length - 2];

    const candlePrice = latestCandle?.close || 0;
    const candleChange = candlePrice - (prevCandle?.close || candlePrice);
    const candlePercent = prevCandle?.close ? ((candleChange / prevCandle.close) * 100) : 0;

    const price = candlePrice > 0 ? candlePrice : (overviewData?.price || 0);
    const percentNum = candlePrice > 0 ? candlePercent : (overviewData?.change || 0);
    const percent = percentNum.toFixed(2);
    const change = candlePrice > 0 ? candleChange : (price * percentNum / 100);
    const isUp = percentNum > 0;
    const isDown = percentNum < 0;

    // 🕒 Lấy giờ hiện tại (1 lần khi render)
    const now = new Date();
    const timeVN = new Intl.DateTimeFormat("vi-VN", {
        timeZone: "Asia/Ho_Chi_Minh",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
    }).format(now);

    return (
        <div className="max-w-[90vw] mx-auto flex flex-col gap-6 py-6">
            <div className="bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 rounded-2xl p-6 shadow-sm transition-colors">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                    {/* Left info */}
                    <div>
                        <h1 className="text-xl font-bold text-slate-900 dark:text-white flex items-center gap-2.5">
                            <span className="px-2.5 py-0.5 rounded-lg text-sm font-black bg-indigo-600/10 dark:bg-indigo-500/20 text-indigo-600 dark:text-indigo-400 border border-indigo-500/30">
                                {symbol}
                            </span>
                            <span>{companyDisplayName}</span>
                        </h1>
                        <div className="flex items-center text-sm text-slate-500 dark:text-slate-400 mt-1.5 gap-2">
                            <span className="flex items-center gap-1 font-mono font-semibold text-slate-700 dark:text-slate-300">
                                <Clock
                                    size={14}
                                    strokeWidth={2}
                                    className="text-amber-500"
                                />
                                {symbol}:HSX
                            </span>
                            <span>•</span>
                            <span className="text-xs text-slate-400">
                                Cập nhật: {timeVN} (GMT+7)
                            </span>
                            <Star
                                size={15}
                                strokeWidth={1.6}
                                className="ml-2 text-slate-400 hover:text-yellow-400 cursor-pointer transition-colors"
                            />
                        </div>
                    </div>

                    {/* Right info */}
                    <div className="text-left sm:text-right">
                        <p className="text-3xl font-extrabold text-slate-900 dark:text-white leading-none font-mono">
                            {price > 0 ? price.toFixed(2) : "—"}
                        </p>
                        {price > 0 && (
                            <p
                                className={`mt-1.5 text-sm font-bold font-mono ${isUp
                                        ? "text-emerald-600 dark:text-emerald-400"
                                        : isDown
                                            ? "text-red-600 dark:text-rose-400"
                                            : "text-slate-500 dark:text-slate-400"
                                    }`}
                            >
                                {change > 0 ? "+" : ""}
                                {change.toFixed(2)} / {percent}%
                            </p>
                        )}
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2 space-y-6">
                    <TradingViewWidget symbol={symbol} />

                    <div className="w-full">
                        <NewsListJson />
                    </div>
                </div>

                <div>
                    <StockInfoCard symbol={symbol} />
                </div>
            </div>
        </div>
    );
}
