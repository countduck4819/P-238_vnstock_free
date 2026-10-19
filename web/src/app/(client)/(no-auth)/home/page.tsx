"use client";

import LeftSidebar from "@/share/components/home/LeftSidebar";
import StockRecommendationTabs from "@/share/components/home/StockRecommendationTabs";
import MarketNewsFeed from "@/share/components/home/MarketNewsFeed";
import CommunityPostsWidget from "@/share/components/home/CommunityPostsWidget";
import { useEffect, useRef, useState } from "react";
import { useTheme } from "@/components/theme/ThemeProvider";
import { useAuth } from "@/auth/AuthProvider";
import { AccountType } from "@/store/users/user.reducer";
import { Role } from "@/share/enum";
import {
    Activity,
    LineChart as ChartIcon,
    TrendingUp,
    TrendingDown,
    Sparkles,
} from "lucide-react";

declare global {
    interface Window {
        TradingView?: {
            widget: new (config: Record<string, unknown>) => void;
        };
    }
}

const SYMBOL_MAP: Record<string, string> = {
    VNINDEX: "HOSE:VNINDEX",
    HNXINDEX: "HNX:HNXINDEX",
    UPINDEX: "HNX:301",
    VN30: "HNX:100",
    VN30F1M: "HNX:VN301!",
    FPT: "HOSE:FPT",
    HPG: "HOSE:HPG",
    VCB: "HOSE:VCB",
    SSI: "HOSE:SSI",
    MWG: "HOSE:MWG",
    TCB: "HOSE:TCB",
    MBB: "HOSE:MBB",
};

const MOCK_INDICES = [
    {
        code: "HNXINDEX",
        name: "Chỉ số HNX-Index",
        exchange: "HNX",
        value: "234.10",
        change: "+1.12 (+0.48%)",
    },
    {
        code: "UPINDEX",
        name: "Chỉ số UPCoM",
        exchange: "UPCOM",
        value: "89.05",
        change: "-0.21 (-0.23%)",
    },
    {
        code: "VN30",
        name: "Chỉ số VN30",
        exchange: "HOSE",
        value: "1,245.77",
        change: "+4.10 (+0.33%)",
    },
];

export default function HomePage() {
    const containerRef = useRef<HTMLDivElement | null>(null);
    const [tvReady, setTvReady] = useState(false);
    const [current, setCurrent] = useState<string>("HNXINDEX");
    const [indices, setIndices] = useState(MOCK_INDICES);
    const { resolvedTheme } = useTheme();
    const { user } = useAuth();

    const isPremium = user?.accountType === AccountType.PREMIUM || user?.role === Role.Admin;

    useEffect(() => {
        const fetchOverview = async () => {
            try {
                const res = await fetch("/api/stocks/overview");
                if (res.ok) {
                    const json = await res.json();
                    const data = json?.data || json;
                    if (data && typeof data === "object") {
                        setIndices((prev) =>
                            prev.map((item) => {
                                const live = data[item.code];
                                if (live && live.price) {
                                    const sign = live.change >= 0 ? "+" : "";
                                    return {
                                        ...item,
                                        value: Number(live.price).toLocaleString("vi-VN", {
                                            minimumFractionDigits: 2,
                                            maximumFractionDigits: 2,
                                        }),
                                        change: `${sign}${Number(live.change).toFixed(2)}%`,
                                    };
                                }
                                return item;
                            })
                        );
                    }
                }
            } catch {
                // Ignore
            }
        };
        void fetchOverview();
    }, []);

    useEffect(() => {
        if (window?.TradingView) {
            setTvReady(true);
            return;
        }
        const script = document.createElement("script");
        script.src = "https://s3.tradingview.com/tv.js";
        script.async = true;
        script.onload = () => setTvReady(true);
        document.body.appendChild(script);
    }, []);

    const createWidget = (symbolKey: string) => {
        if (!tvReady || !window?.TradingView || !containerRef.current) return;
        const tvSymbol = SYMBOL_MAP[symbolKey] || (symbolKey.includes(":") ? symbolKey : `HOSE:${symbolKey}`);

        containerRef.current.innerHTML = "";

        const newId = `tv-container-${symbolKey}-${Date.now()}`;
        containerRef.current.id = newId;

        const isDark = resolvedTheme === "dark";

        new window.TradingView.widget({
            symbol: tvSymbol,
            interval: "D",
            container_id: newId,
            width: "100%",
            height: isPremium ? 460 : 380,
            timezone: "Asia/Ho_Chi_Minh",
            theme: isDark ? "dark" : "light",
            style: "1",
            locale: "vi",
            toolbar_bg: isDark ? "#090d16" : "#f8fafc",
            enable_publishing: false,
            allow_symbol_change: true,
            hide_side_toolbar: !isPremium,
            hide_top_toolbar: false,
            withdateranges: true,
            details: true,
            hotlist: false,
            calendar: false,
            studies: isPremium
                ? ["MASimple@tv-basicstudies", "RSI@tv-basicstudies", "MACD@tv-basicstudies"]
                : ["MASimple@tv-basicstudies", "MASimple@tv-basicstudies"],
        });
    };

    useEffect(() => {
        if (tvReady) createWidget(current);
    }, [tvReady, resolvedTheme, isPremium]);

    useEffect(() => {
        if (tvReady) createWidget(current);
    }, [current]);

    return (
        <div className="min-h-screen bg-slate-50/50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 transition-colors">
            {/* Top subtle glow banner */}
            <div className="pointer-events-none fixed top-14 left-1/2 -translate-x-1/2 w-[80vw] h-[300px] bg-gradient-to-r from-indigo-500/5 via-purple-500/5 to-pink-500/5 blur-3xl -z-10" />

            <main className="max-w-[92vw] 2xl:max-w-[1600px] mx-auto px-2 sm:px-4 py-5 md:py-6">
                <section className="flex flex-col lg:grid lg:grid-cols-[1fr_380px] xl:grid-cols-[1fr_420px] gap-5 items-start">
                    {/* LEFT COLUMN: Main Tabs & Stock Recommendations */}
                    <div className="w-full space-y-4 min-w-0">
                        <LeftSidebar onPickSymbol={(sym) => setCurrent(sym)} currentSymbol={current} />

                        <StockRecommendationTabs />

                        {/* Trên điện thoại cột phải bị ẩn nên bài đăng cộng đồng nằm trên bảng tin */}
                        <div className="lg:hidden">
                            <CommunityPostsWidget limit={3} />
                        </div>

                        <MarketNewsFeed />
                    </div>

                    {/* RIGHT COLUMN (Desktop): biểu đồ, chỉ số, bài đăng cộng đồng */}
                    <div className="hidden lg:block w-full space-y-4 lg:self-stretch">
                        {/* 1. BIỂU ĐỒ KỸ THUẬT (Only shown for Free users as a preview; Premium has the main chart in Software tab) */}
                        {!isPremium && (
                            <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm overflow-hidden transition-all">
                                {/* Chart Card Header */}
                                <div className="px-4 py-3 border-b border-slate-200/80 dark:border-slate-800 flex items-center justify-between bg-slate-50/70 dark:bg-slate-900/90">
                                    <div className="flex items-center gap-2">
                                        <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                                        <h2 className="text-xs md:text-sm font-bold text-slate-900 dark:text-white flex items-center gap-1.5">
                                            <span>Biểu đồ kỹ thuật</span>
                                            <span className="px-2 py-0.5 rounded-md text-[11px] font-bold bg-indigo-500/10 text-indigo-600 dark:text-indigo-400">
                                                {current}
                                            </span>
                                        </h2>
                                    </div>

                                    <div className="flex items-center gap-1.5 text-[11px] font-medium text-slate-500 dark:text-slate-400">
                                        <ChartIcon size={14} className="text-indigo-500" />
                                        <span>TradingView D1</span>
                                    </div>
                                </div>

                                {/* Chart Container */}
                                <div className="p-0 bg-slate-50/30 dark:bg-slate-950/40">
                                    <div
                                        id="tv-container"
                                        ref={containerRef}
                                        className="w-full min-h-[340px] sm:min-h-[380px]"
                                    />
                                </div>
                            </div>
                        )}

                        {/* 2. CHỈ SỐ THỊ TRƯỜNG (Market Indices Sidebar) */}
                        <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm overflow-hidden">
                            <div className="px-4 py-3 border-b border-slate-200/80 dark:border-slate-800 flex items-center justify-between bg-slate-50/70 dark:bg-slate-900/90">
                                <div className="flex items-center gap-2">
                                    <Activity size={16} className="text-indigo-600 dark:text-indigo-400" />
                                    <h3 className="text-xs md:text-sm font-bold text-slate-900 dark:text-white">
                                        Chỉ số thị trường
                                    </h3>
                                </div>
                                <span className="text-[10px] font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider">
                                    Realtime Feed
                                </span>
                            </div>

                            {/* Indices List */}
                            <div className="p-2 space-y-1.5 bg-slate-50/30 dark:bg-slate-900/50">
                                {indices.map((item) => {
                                    const isActive = item.code === current;
                                    const isDown = item.change.trim().startsWith("-");
                                    const TrendIcon = isDown ? TrendingDown : TrendingUp;

                                    return (
                                        <button
                                            key={item.code}
                                            onClick={() => setCurrent(item.code)}
                                            className={`
                                                w-full text-left p-3 rounded-xl transition-all duration-200 cursor-pointer border
                                                ${
                                                    isActive
                                                        ? "bg-white dark:bg-slate-800 border-indigo-500/40 dark:border-indigo-500/40 shadow-xs ring-1 ring-indigo-500/20"
                                                        : "bg-white/70 dark:bg-slate-900/70 border-slate-200/70 dark:border-slate-800 hover:bg-white dark:hover:bg-slate-800/80 hover:border-slate-300 dark:hover:border-slate-700"
                                                }
                                            `}
                                        >
                                            <div className="flex items-center justify-between">
                                                <div className="flex items-center gap-2">
                                                    <span className="font-bold text-xs md:text-sm text-slate-900 dark:text-white">
                                                        {item.code}
                                                    </span>
                                                    <span className="px-1.5 py-0.2 rounded text-[10px] font-medium bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400">
                                                        {item.exchange}
                                                    </span>
                                                </div>

                                                <div className="font-mono font-bold text-xs md:text-sm text-slate-900 dark:text-white">
                                                    {item.value}
                                                </div>
                                            </div>

                                            <div className="mt-1 flex items-center justify-between text-xs">
                                                <div className="text-[11px] text-slate-500 dark:text-slate-400 truncate pr-2">
                                                    {item.name}
                                                </div>

                                                <div
                                                    className={`inline-flex items-center gap-1 font-mono font-semibold text-[11px] px-2 py-0.5 rounded-md ${
                                                        isDown
                                                            ? "bg-rose-500/10 text-rose-600 dark:text-rose-400"
                                                            : "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                                                    }`}
                                                >
                                                    <TrendIcon size={12} />
                                                    <span>{item.change}</span>
                                                </div>
                                            </div>
                                        </button>
                                    );
                                })}
                            </div>
                        </div>

                        {/* Cột phải cao bằng cột tin tức nên khối này bám theo khi cuộn bảng tin */}
                        <div className="sticky top-20 max-h-[calc(100dvh-6rem)] overflow-y-auto no-scrollbar rounded-2xl">
                            <CommunityPostsWidget />
                        </div>
                    </div>
                </section>
            </main>
        </div>
    );
}
