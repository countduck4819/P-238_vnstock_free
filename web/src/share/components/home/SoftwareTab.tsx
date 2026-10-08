import { useState, useMemo, useRef, useEffect } from "react";
import Image from "next/image";
import { Inter } from "next/font/google";
import { AnimatePresence, easeInOut, motion } from "framer-motion";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import {
    BookOpen,
    CircleUserRound,
    HelpCircle,
    CheckCircle2,
    Sparkles,
    ArrowRight,
    Download,
    Laptop,
    Smartphone,
    Layers,
    FileSpreadsheet,
    PieChart,
    Bot,
    TrendingUp,
    TrendingDown,
    Activity,
    Zap,
    LineChart as ChartIcon,
    Globe,
    QrCode,
    ExternalLink,
    Lock,
    Share2,
} from "lucide-react";
import { cn } from "@/lib/utils";

import Link from "next/link";
import { useAuth } from "@/auth/AuthProvider";
import { AccountType } from "@/store/users/user.reducer";
import { Role } from "@/share/enum";
import { useTheme } from "@/components/theme/ThemeProvider";
import {
    HoverCard,
    HoverCardContent,
    HoverCardTrigger,
} from "@/components/ui/hover-card";

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

const SYMBOL_MAP: Record<string, string> = {
    HNXINDEX: "HNX:HNXINDEX",
    VNINDEX: "HOSE:VNINDEX",
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

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

type TabKey = "web" | "mobile" | "amibroker" | "excel" | "infographic" | "ai";

const TAB_ITEMS: Array<{
    key: TabKey;
    label: string;
    desc: string;
    icon: any;
    tag?: string;
}> = [
        {
            key: "web",
            label: "Web - PC",
            desc: "Nền tảng phân tích trên máy tính",
            icon: Laptop,
        },
        {
            key: "mobile",
            label: "Web Mobile",
            desc: "Tối ưu cho trình duyệt điện thoại",
            icon: Smartphone,
        },
        {
            key: "amibroker",
            label: "AmiBroker",
            desc: "Dữ liệu cho AmiBroker/MetaStock",
            icon: Layers,
        },
        {
            key: "excel",
            label: "Excel",
            desc: "Khai thác dữ liệu trên Excel",
            icon: FileSpreadsheet,
        },
        {
            key: "infographic",
            label: "Infographic",
            desc: "Báo cáo phân tích cập nhật",
            icon: PieChart,
        },
        {
            key: "ai",
            label: "Trợ lý AI",
            desc: "Trợ lý AI cho NĐT CK",
            icon: Bot,
            tag: "NEW",
        },
    ];

const WEB_CONTENT = {
    title: "Nền tảng phân tích, công cụ đầu tư chứng khoán trên máy tính",
    featuresLeft: [
        "Công nghệ hiện đại & dữ liệu realtime",
        "Phân tích kỹ thuật đa biểu đồ, đa khung thời gian",
        "Cộng đồng sôi nổi, tương tác cùng chuyên gia",
    ],
    featuresRight: [
        "Tùy biến giao diện làm việc linh hoạt",
        "Tin tức đa chiều, cập nhật liên tục 24/7",
        "Bộ lọc cổ phiếu thông minh & tìm kiếm cơ hội",
    ],
    images: [
        "/img/web-widescreen.jpg",
        "/img/web-features-01.jpg",
        "/img/web-features-02.jpg",
    ],
};

export default function FinSightSoftware({ onSelect, currentSymbol = "HNXINDEX" }: { onSelect?: (symbol: string) => void; currentSymbol?: string }) {
    const [active, setActive] = useState<TabKey>("web");
    const [selectedSymbol, setSelectedSymbol] = useState<string>(currentSymbol || "HNXINDEX");
    const tvContainerRef = useRef<HTMLDivElement | null>(null);
    const { resolvedTheme } = useTheme();
    const { user } = useAuth();

    const isPremium = user?.accountType === AccountType.PREMIUM || user?.role === Role.Admin;

    const [isMobileClient, setIsMobileClient] = useState<boolean>(false);
    const [indices, setIndices] = useState(MOCK_INDICES);

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
        const checkDevice = () => {
            if (typeof window === "undefined") return;
            const isMobileWidth = window.innerWidth < 768;
            const isMobileUA =
                /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(
                    navigator.userAgent
                );
            setIsMobileClient(isMobileWidth || isMobileUA);
        };
        checkDevice();
        window.addEventListener("resize", checkDevice);
        return () => window.removeEventListener("resize", checkDevice);
    }, []);

    const dynamicTabItems = useMemo(() => {
        if (isMobileClient) {
            return [
                {
                    key: "web" as TabKey,
                    label: "Web Mobile",
                    desc: "Trải nghiệm trên điện thoại",
                    icon: Smartphone,
                },
                {
                    key: "mobile" as TabKey,
                    label: "Bản Web PC",
                    desc: "Phân tích nâng cao trên Máy tính",
                    icon: Laptop,
                },
                ...TAB_ITEMS.slice(2),
            ];
        }

        return [
            {
                key: "web" as TabKey,
                label: "Web - PC",
                desc: "Nền tảng phân tích trên máy tính",
                icon: Laptop,
            },
            {
                key: "mobile" as TabKey,
                label: "Web Mobile",
                desc: "Tối ưu cho trình duyệt điện thoại",
                icon: Smartphone,
            },
            ...TAB_ITEMS.slice(2),
        ];
    }, [isMobileClient]);

    const [tvReady, setTvReady] = useState(false);

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

    useEffect(() => {
        if (currentSymbol) {
            setSelectedSymbol(currentSymbol);
        }
    }, [currentSymbol]);

    const handlePickTicker = (t: string) => {
        setSelectedSymbol(t);
        if (onSelect) {
            onSelect(t);
        }
    };

    useEffect(() => {
        if (!isPremium || active !== "web") return;
        if (typeof window === "undefined" || !tvReady || !window.TradingView || !tvContainerRef.current) return;

        const tvSymbol = SYMBOL_MAP[selectedSymbol] || (selectedSymbol.includes(":") ? selectedSymbol : `HOSE:${selectedSymbol}`);
        tvContainerRef.current.innerHTML = "";
        const newId = `tv-software-container-${selectedSymbol}-${Date.now()}`;
        tvContainerRef.current.id = newId;

        const isDark = resolvedTheme === "dark";

        new window.TradingView.widget({
            symbol: tvSymbol,
            interval: "D",
            container_id: newId,
            width: "100%",
            height: 560,
            timezone: "Asia/Ho_Chi_Minh",
            theme: isDark ? "dark" : "light",
            style: "1",
            locale: "vi",
            toolbar_bg: isDark ? "#090d16" : "#f8fafc",
            enable_publishing: false,
            allow_symbol_change: true,
            hide_side_toolbar: false,
            hide_top_toolbar: false,
            withdateranges: true,
            details: true,
            hotlist: false,
            calendar: false,
            studies: ["MASimple@tv-basicstudies", "RSI@tv-basicstudies", "MACD@tv-basicstudies"],
        });
    }, [isPremium, active, selectedSymbol, resolvedTheme, tvReady]);

    const fade = useMemo(
        () => ({
            initial: { opacity: 0, y: 6 },
            animate: { opacity: 1, y: 0 },
            exit: { opacity: 0, y: -6 },
            transition: {
                duration: 0.22,
                ease: easeInOut,
            },
        }),
        []
    );

    return (
        <main
            className={cn("w-full font-sans text-slate-900 dark:text-slate-100", inter.variable)}
            style={{ fontFamily: "var(--font-inter)" }}
        >
            {/* TOP BAR: Title + Guides + Membership Banner */}
            <div className="mb-4 space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                        <div className="w-2.5 h-2.5 rounded-full bg-indigo-600 dark:bg-indigo-400" />
                        <h2 className="font-bold text-base md:text-lg text-slate-900 dark:text-white tracking-tight">
                            Phần mềm FinSight
                        </h2>
                    </div>

                    <div className="flex items-center gap-3 text-xs md:text-sm font-medium text-indigo-600 dark:text-indigo-400">
                        <Link
                            href="/ve-chung-toi"
                            className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-colors"
                        >
                            <BookOpen size={15} />
                            <span>Giới thiệu</span>
                        </Link>

                        <HoverCard>
                            <HoverCardTrigger asChild>
                                <button className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-colors cursor-pointer">
                                    <HelpCircle size={15} />
                                    <span>Hướng dẫn</span>
                                </button>
                            </HoverCardTrigger>

                            <HoverCardContent className="w-72 bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-200 shadow-xl rounded-xl p-4 text-xs leading-relaxed">
                                <p className="font-semibold text-slate-900 dark:text-white mb-1">
                                    Trung tâm Trợ giúp FinSight
                                </p>
                                <p>
                                    Xem hướng dẫn thao tác chi tiết từng bước, video minh họa và các mẹo phân tích kỹ thuật nâng cao.
                                </p>
                            </HoverCardContent>
                        </HoverCard>
                    </div>
                </div>

                {/* MEMBERSHIP STATUS CARD (Adaptive: hides upgrade button for Premium) */}
                <div className="relative overflow-hidden rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-gradient-to-r from-slate-50 via-indigo-50/30 to-white dark:from-slate-900 dark:via-indigo-950/20 dark:to-slate-900 p-3.5 md:p-4 shadow-sm">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                        <div className="flex items-center gap-3">
                            <div className={`w-10 h-10 rounded-xl flex items-center justify-center border ${isPremium
                                    ? "bg-amber-500/10 text-amber-500 border-amber-500/30"
                                    : "bg-indigo-600/10 dark:bg-indigo-400/10 text-indigo-600 dark:text-indigo-400 border-indigo-500/20"
                                }`}>
                                {isPremium ? <Sparkles size={20} /> : <CircleUserRound size={22} />}
                            </div>
                            <div>
                                <p className="text-xs text-slate-500 dark:text-slate-400 font-medium">
                                    Gói tài khoản hiện tại
                                </p>
                                <div className="flex items-center gap-2">
                                    <span className="font-bold text-sm text-slate-900 dark:text-white">
                                        {isPremium ? "Hội viên Cao cấp" : "Hội viên Miễn phí"}
                                    </span>
                                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold border ${isPremium
                                            ? "bg-gradient-to-r from-amber-500/20 to-orange-500/20 text-amber-600 dark:text-amber-400 border-amber-500/30"
                                            : "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20"
                                        }`}>
                                        {isPremium ? "PREMIUM PRO" : "FREE"}
                                    </span>
                                </div>
                            </div>
                        </div>

                        {isPremium ? (
                            <div className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 text-xs font-semibold">
                                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                                <span>Đã mở khóa toàn bộ tính năng & Biểu đồ PRO</span>
                            </div>
                        ) : (
                            <Link href="/nang-cap-hoi-vien">
                                <Button
                                    size="sm"
                                    className="bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white text-xs font-semibold px-4 py-2 rounded-xl shadow-md shadow-indigo-500/20 hover:shadow-indigo-500/30 transition-all duration-200 cursor-pointer"
                                >
                                    <Sparkles className="w-3.5 h-3.5 mr-1" />
                                    Nâng cấp / Gia hạn
                                </Button>
                            </Link>
                        )}
                    </div>
                </div>
            </div>

            {/* MAIN CONTAINER: Full width for Premium, 2-column for Free */}
            <Tabs
                value={active}
                onValueChange={(v) => setActive(v as TabKey)}
                className="w-full"
            >
                {isPremium ? (
                    /* PREMIUM PRO LAYOUT: 100% focused on massive TradingView Technical Chart */
                    <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm overflow-hidden p-3 sm:p-4 space-y-3">
                        {/* FULL WIDTH TRADINGVIEW CHART */}
                        <div className="w-full space-y-3">
                            {/* Chart Header Bar */}
                            <div className="flex flex-wrap items-center justify-between gap-2 pb-2 border-b border-slate-100 dark:border-slate-800">
                                <div className="flex items-center gap-2">
                                    <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
                                    <h3 className="text-sm md:text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
                                        <span>Biểu đồ kỹ thuật</span>
                                        <span className="px-2.5 py-0.5 rounded-md text-xs font-bold bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border border-indigo-500/20">
                                            {selectedSymbol}
                                        </span>
                                    </h3>
                                </div>

                                <div className="flex items-center gap-1.5 text-xs font-medium text-slate-500 dark:text-slate-400">
                                    <ChartIcon size={14} className="text-indigo-500" />
                                    <span>TradingView D1</span>
                                </div>
                            </div>

                            {/* Chart Container (Massive 560px Height on Desktop, 380px on Mobile) */}
                            <div className="rounded-xl overflow-hidden border border-slate-200/80 dark:border-slate-800 bg-slate-50/40 dark:bg-slate-950/50 shadow-inner">
                                <div
                                    id="tv-software-container"
                                    ref={tvContainerRef}
                                    className="w-full h-[360px] sm:h-[460px] lg:h-[560px]"
                                />
                            </div>

                            {/* CHỈ SỐ THỊ TRƯỜNG (Market Indices - Đi liền ngay dưới Biểu đồ kỹ thuật) */}
                            <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm overflow-hidden mt-3">
                                <div className="px-4 py-2.5 border-b border-slate-200/80 dark:border-slate-800 flex items-center justify-between bg-slate-50/70 dark:bg-slate-900/90">
                                    <div className="flex items-center gap-2">
                                        <Activity size={15} className="text-indigo-600 dark:text-indigo-400" />
                                        <h4 className="text-xs md:text-sm font-bold text-slate-900 dark:text-white">
                                            Chỉ số thị trường
                                        </h4>
                                    </div>
                                    <span className="text-[10px] font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider">
                                        Chọn mã để xem biểu đồ
                                    </span>
                                </div>

                                {/* Indices Grid */}
                                <div className="p-2 grid grid-cols-1 sm:grid-cols-3 gap-2 bg-slate-50/30 dark:bg-slate-900/50">
                                    {indices.map((item) => {
                                        const isActive = item.code === selectedSymbol;
                                        const isDown = item.change.trim().startsWith("-");
                                        const TrendIcon = isDown ? TrendingDown : TrendingUp;

                                        return (
                                            <button
                                                key={item.code}
                                                type="button"
                                                onClick={() => handlePickTicker(item.code)}
                                                className={`
                                                    w-full text-left p-2.5 rounded-xl transition-all duration-200 cursor-pointer border
                                                    ${isActive
                                                        ? "bg-white dark:bg-slate-800 border-indigo-500/50 dark:border-indigo-500/50 shadow-xs ring-1 ring-indigo-500/30"
                                                        : "bg-white/80 dark:bg-slate-900/80 border-slate-200/70 dark:border-slate-800 hover:bg-white dark:hover:bg-slate-800 hover:border-slate-300 dark:hover:border-slate-700"
                                                    }
                                                `}
                                            >
                                                <div className="flex items-center justify-between">
                                                    <div className="flex items-center gap-1.5">
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
                                                        className={`inline-flex items-center gap-1 font-mono font-semibold text-[11px] px-1.5 py-0.5 rounded-md shrink-0 ${isDown
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
                        </div>
                    </div>
                ) : (
                    /* FREE LAYOUT: 2-Column with Left Vertical Tabs & Right Preview */
                    <div className="grid grid-cols-1 lg:grid-cols-[230px_1fr] rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm overflow-hidden">
                        {/* LEFT SUBTABS LIST */}
                        <div className="bg-slate-50/60 dark:bg-slate-900/60 border-b lg:border-b-0 lg:border-r border-slate-200/80 dark:border-slate-800 p-2 sm:p-2.5 overflow-x-auto no-scrollbar">
                            <TabsList className="flex flex-row lg:flex-col items-stretch h-auto bg-transparent p-0 gap-2 w-max lg:w-full">
                                {dynamicTabItems.map((item) => {
                                    const Icon = item.icon;
                                    const isActive = active === item.key;
                                    return (
                                        <TabsTrigger
                                            key={item.key}
                                            value={item.key}
                                            className={cn(
                                                "shrink-0 lg:shrink-1 min-w-[135px] sm:min-w-[160px] lg:min-w-0 w-auto lg:w-full relative flex items-center lg:items-start gap-2.5 sm:gap-3 px-3 py-2.5 sm:p-3 rounded-xl text-left transition-all duration-200 select-none cursor-pointer border border-transparent",
                                                isActive
                                                    ? "bg-white dark:bg-slate-800/90 text-indigo-600 dark:text-white shadow-sm border-slate-200/80 dark:border-slate-700/80 font-semibold"
                                                    : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 hover:bg-white/50 dark:hover:bg-slate-800/50"
                                            )}
                                        >
                                            <div
                                                className={cn(
                                                    "w-8 h-8 sm:w-9 sm:h-9 rounded-lg flex items-center justify-center shrink-0 transition-colors",
                                                    isActive
                                                        ? "bg-indigo-600 text-white shadow-sm shadow-indigo-500/30"
                                                        : "bg-slate-200/70 dark:bg-slate-800 text-slate-600 dark:text-slate-400"
                                                )}
                                            >
                                                <Icon size={17} className="shrink-0" />
                                            </div>

                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-1.5">
                                                    <span className={cn("text-xs md:text-sm font-semibold truncate", isActive ? "text-indigo-600 dark:text-white" : "text-slate-800 dark:text-slate-200")}>
                                                        {item.label}
                                                    </span>
                                                    {item.tag && (
                                                        <span className="px-1.5 py-0.2 rounded-full text-[9px] font-bold bg-gradient-to-r from-rose-500 to-pink-500 text-white tracking-wider animate-pulse">
                                                            {item.tag}
                                                        </span>
                                                    )}
                                                </div>
                                                <p className="text-[11px] text-slate-500 dark:text-slate-400 truncate mt-0.5 font-normal hidden sm:block">
                                                    {item.desc}
                                                </p>
                                            </div>
                                        </TabsTrigger>
                                    );
                                })}
                            </TabsList>
                        </div>

                        {/* RIGHT CONTENT DISPLAY */}
                        <div className="relative w-full p-4 md:p-5 bg-white dark:bg-slate-900 flex flex-col justify-center min-h-[380px]">
                            <AnimatePresence mode="wait">
                                {/* 1. WEB - PC */}
                                {active === "web" && (
                                    <motion.div
                                        key="web"
                                        {...fade}
                                        className="w-full space-y-5"
                                    >
                                        <div className="text-center md:text-left space-y-1">
                                            <h3 className="text-base md:text-xl font-bold text-slate-900 dark:text-white leading-snug">
                                                {isMobileClient
                                                    ? "Trải nghiệm mượt mà trên Trình duyệt Điện thoại"
                                                    : WEB_CONTENT.title}
                                            </h3>
                                            <p className="text-xs md:text-sm text-slate-500 dark:text-slate-400">
                                                {isMobileClient
                                                    ? "Theo dõi bảng giá realtime, biểu đồ nến và trợ lý AI trực tiếp trên Safari / Chrome mà không cần cài đặt app."
                                                    : "Công cụ giao dịch và biểu đồ phân tích kỹ thuật chuẩn quốc tế cho nhà đầu tư Việt Nam"}
                                            </p>
                                        </div>

                                        {/* Feature Checkmarks */}
                                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
                                            {[
                                                ...WEB_CONTENT.featuresLeft,
                                                ...WEB_CONTENT.featuresRight,
                                            ].map((feat, idx) => (
                                                <div
                                                    key={idx}
                                                    className="flex items-center gap-2.5 text-xs text-slate-700 dark:text-slate-300"
                                                >
                                                    <div className="w-4 h-4 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 flex items-center justify-center shrink-0">
                                                        <CheckCircle2 size={13} />
                                                    </div>
                                                    <span className="font-medium">{feat}</span>
                                                </div>
                                            ))}
                                        </div>

                                        {/* Previews */}
                                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2">
                                            {WEB_CONTENT.images.map((src, i) => (
                                                <div
                                                    key={i}
                                                    className="group relative rounded-xl overflow-hidden border border-slate-200/90 dark:border-slate-800 bg-slate-100 dark:bg-slate-800/60 shadow-sm hover:shadow-md transition-all"
                                                >
                                                    <div className="h-4 bg-slate-200/60 dark:bg-slate-800 px-2 flex items-center gap-1 border-b border-slate-200 dark:border-slate-700">
                                                        <div className="w-1.5 h-1.5 rounded-full bg-rose-400" />
                                                        <div className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                                                        <div className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                                                    </div>
                                                    <Image
                                                        src={src}
                                                        alt={`preview-${i}`}
                                                        width={360}
                                                        height={200}
                                                        className="object-cover w-full h-[6.5rem] group-hover:scale-105 transition-transform duration-300"
                                                    />
                                                </div>
                                            ))}
                                        </div>
                                    </motion.div>
                                )}

                                {/* 2. ADAPTIVE CROSS-PLATFORM PROMOTION TAB */}
                                {active === "mobile" && (
                                    <motion.div
                                        key="mobile"
                                        {...fade}
                                        className="w-full"
                                    >
                                        {/* IF USER IS ON MOBILE -> PROMOTE WEB PC */}
                                        {isMobileClient ? (
                                            <div className="grid grid-cols-1 md:grid-cols-2 gap-8 items-center">
                                                {/* Laptop preview mockup */}
                                                <div className="flex justify-center">
                                                    <div className="relative w-full max-w-[340px] aspect-[16/10] rounded-2xl border-4 border-slate-800 dark:border-slate-700 bg-slate-950 p-2.5 shadow-2xl shadow-indigo-500/10 flex flex-col justify-between">
                                                        {/* Screen top bar */}
                                                        <div className="flex items-center justify-between px-2.5 py-1 bg-slate-900 rounded-lg text-[9px] text-slate-400 mb-1.5 border border-slate-800">
                                                            <div className="flex items-center gap-1.5">
                                                                <div className="w-1.5 h-1.5 rounded-full bg-rose-400" />
                                                                <div className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                                                                <div className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                                                            </div>
                                                            <div className="flex items-center gap-1 text-slate-200 font-medium">
                                                                <Lock className="w-2.5 h-2.5 text-emerald-400" />
                                                                <span>c4-app-238.io.vn/dashboard</span>
                                                            </div>
                                                            <span className="text-[8px] text-indigo-400 font-bold">PRO WORKSPACE</span>
                                                        </div>

                                                        {/* Simulated Multi-Chart Workspace */}
                                                        <div className="flex-1 bg-slate-900/90 rounded-lg border border-slate-800 p-2 flex flex-col justify-between overflow-hidden">
                                                            <div className="grid grid-cols-2 gap-2 h-full">
                                                                <div className="rounded bg-slate-950/80 border border-slate-800 p-1.5 flex flex-col justify-between">
                                                                    <div className="flex justify-between text-[8px] text-slate-400">
                                                                        <span className="font-bold text-white">VN-INDEX</span>
                                                                        <span className="text-emerald-400 font-semibold">+1.24%</span>
                                                                    </div>
                                                                    <TrendingUp className="w-7 h-7 text-indigo-400 mx-auto my-1" />
                                                                    <div className="h-1.5 bg-slate-800 rounded-full w-3/4" />
                                                                </div>
                                                                <div className="rounded bg-slate-950/80 border border-slate-800 p-1.5 flex flex-col justify-between">
                                                                    <div className="flex justify-between text-[8px] text-slate-400">
                                                                        <span className="font-bold text-white">VN30</span>
                                                                        <span className="text-emerald-400 font-semibold">+0.85%</span>
                                                                    </div>
                                                                    <Activity className="w-7 h-7 text-emerald-400 mx-auto my-1" />
                                                                    <div className="h-1.5 bg-slate-800 rounded-full w-2/3" />
                                                                </div>
                                                            </div>
                                                        </div>

                                                        {/* Laptop keyboard stand base */}
                                                        <div className="h-2 bg-slate-800 rounded-b-xl mt-1.5 mx-4 border-t border-slate-700" />
                                                    </div>
                                                </div>

                                                {/* PC Promo Content */}
                                                <div className="space-y-4">
                                                    <div>
                                                        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border border-indigo-500/20 mb-2.5">
                                                            <Laptop className="w-3.5 h-3.5" />
                                                            <span>Màn hình lớn • Đa biểu đồ chuyên sâu</span>
                                                        </div>
                                                        <h3 className="text-lg md:text-2xl font-bold text-slate-900 dark:text-white leading-snug">
                                                            Nâng tầm Phân tích Kỹ thuật trên Máy tính (PC / Laptop)
                                                        </h3>
                                                        <p className="text-xs md:text-sm text-slate-500 dark:text-slate-400 mt-1.5 leading-relaxed">
                                                            Mở FinSight trên máy tính để sử dụng trọn bộ công cụ giao dịch chuyên nghiệp, đa khung thời gian và bộ lọc cổ phiếu chuyên sâu.
                                                        </p>
                                                    </div>

                                                    {/* Info Box */}
                                                    <div className="p-4 rounded-2xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200/80 dark:border-slate-800 flex items-center gap-3.5">
                                                        <div className="w-11 h-11 rounded-xl bg-indigo-600/10 dark:bg-indigo-500/20 text-indigo-600 dark:text-indigo-400 flex items-center justify-center shrink-0">
                                                            <Globe className="w-5 h-5" />
                                                        </div>
                                                        <div className="space-y-0.5">
                                                            <p className="text-xs font-bold text-slate-900 dark:text-white">
                                                                Địa chỉ truy cập trên Máy tính:
                                                            </p>
                                                            <p className="text-xs font-mono text-indigo-600 dark:text-indigo-400 font-bold">
                                                                https://c4-app-238.io.vn
                                                            </p>
                                                            <p className="text-[11px] text-slate-500 dark:text-slate-400">
                                                                Đăng nhập cùng tài khoản để tự động đồng bộ Watchlist & cấu hình phân tích.
                                                            </p>
                                                        </div>
                                                    </div>

                                                    {/* Feature Checkmarks */}
                                                    <div className="space-y-2.5 text-xs text-slate-700 dark:text-slate-300">
                                                        <div className="flex items-center gap-2.5">
                                                            <CheckCircle2 size={15} className="text-emerald-500 shrink-0" />
                                                            <span><strong>Không gian làm việc rộng lớn:</strong> Xem đồng thời 4 biểu đồ nến kỹ thuật và độ sâu sổ lệnh.</span>
                                                        </div>
                                                        <div className="flex items-center gap-2.5">
                                                            <CheckCircle2 size={15} className="text-emerald-500 shrink-0" />
                                                            <span><strong>Hơn 100+ chỉ báo nâng cao:</strong> RSI, MACD, MA, Bollinger Bands, Ichimoku, Fibonacci.</span>
                                                        </div>
                                                        <div className="flex items-center gap-2.5">
                                                            <CheckCircle2 size={15} className="text-emerald-500 shrink-0" />
                                                            <span><strong>Bộ lọc cổ phiếu thông minh:</strong> Tầm soát cơ hội theo phân tích cơ bản (FA) và kỹ thuật (TA).</span>
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                        ) : (
                                            /* IF USER IS ON PC -> PROMOTE WEB MOBILE WITH QR CODE (NO BUTTON) */
                                            <div className="grid grid-cols-1 md:grid-cols-2 gap-8 items-center">
                                                {/* Phone preview mockup (Mobile Web Browser) */}
                                                <div className="flex justify-center">
                                                    <div className="relative w-[230px] h-[380px] rounded-[36px] border-4 border-slate-800 dark:border-slate-700 bg-slate-950 p-2.5 shadow-2xl shadow-indigo-500/10 overflow-hidden flex flex-col">
                                                        {/* Dynamic Island / Notch */}
                                                        <div className="w-20 h-4 bg-slate-900 rounded-full mx-auto mb-2 flex items-center justify-center border border-slate-800">
                                                            <div className="w-2 h-2 rounded-full bg-slate-950" />
                                                        </div>

                                                        {/* Simulated Mobile Browser Address Bar */}
                                                        <div className="mx-1 mb-2 px-2.5 py-1 rounded-lg bg-slate-900/90 border border-slate-800/80 flex items-center justify-between text-[9px] text-slate-400">
                                                            <div className="flex items-center gap-1">
                                                                <Lock className="w-2.5 h-2.5 text-emerald-400" />
                                                                <span className="text-slate-200 font-medium tracking-tight">c4-app-238.io.vn</span>
                                                            </div>
                                                            <span className="text-slate-500 text-[8px]">AA</span>
                                                        </div>

                                                        {/* Mobile Web Viewport Content */}
                                                        <div className="flex-1 bg-gradient-to-b from-slate-900 via-slate-950 to-slate-950 rounded-[20px] p-2.5 text-white flex flex-col justify-between border border-slate-800/80 overflow-hidden">
                                                            <div>
                                                                {/* Header Index pill */}
                                                                <div className="flex justify-between items-center text-[10px] text-slate-400 mb-2 px-1">
                                                                    <span className="font-semibold text-slate-300">VN-INDEX</span>
                                                                    <span className="text-emerald-400 font-bold bg-emerald-500/10 px-1.5 py-0.5 rounded">+1.24%</span>
                                                                </div>
                                                                {/* Chart widget simulation */}
                                                                <div className="h-20 rounded-xl bg-gradient-to-br from-indigo-950/60 to-purple-950/40 border border-indigo-500/30 p-2 flex flex-col justify-between relative overflow-hidden">
                                                                    <div className="flex justify-between items-center text-[9px]">
                                                                        <span className="text-indigo-300 font-medium">Biểu đồ Realtime</span>
                                                                        <span className="text-emerald-400 font-bold">1,288.6 pts</span>
                                                                    </div>
                                                                    <div className="flex items-center justify-center py-1">
                                                                        <TrendingUp className="w-8 h-8 text-indigo-400" />
                                                                    </div>
                                                                    <div className="flex gap-1 text-[7px] text-slate-400 justify-end">
                                                                        <span className="px-1 py-0.2 bg-indigo-500/20 text-indigo-300 rounded font-medium">1D</span>
                                                                        <span className="px-1 py-0.2 bg-slate-800 rounded">1W</span>
                                                                        <span className="px-1 py-0.2 bg-slate-800 rounded">1M</span>
                                                                    </div>
                                                                </div>
                                                            </div>

                                                            {/* Watchlist Quick Rows */}
                                                            <div className="space-y-1 my-2">
                                                                <div className="flex justify-between items-center p-1.5 rounded-lg bg-slate-900/60 border border-slate-800/60 text-[9px]">
                                                                    <div className="flex items-center gap-1.5">
                                                                        <span className="font-bold text-indigo-400">FPT</span>
                                                                        <span className="text-slate-400 text-[8px]">Công nghệ</span>
                                                                    </div>
                                                                    <span className="text-emerald-400 font-semibold">+2.8%</span>
                                                                </div>
                                                                <div className="flex justify-between items-center p-1.5 rounded-lg bg-slate-900/60 border border-slate-800/60 text-[9px]">
                                                                    <div className="flex items-center gap-1.5">
                                                                        <span className="font-bold text-indigo-400">VND</span>
                                                                        <span className="text-slate-400 text-[8px]">Chứng khoán</span>
                                                                    </div>
                                                                    <span className="text-emerald-400 font-semibold">+1.5%</span>
                                                                </div>
                                                            </div>

                                                            {/* Bottom Mobile Tab Bar */}
                                                            <div className="pt-1 border-t border-slate-800/80 flex justify-around text-[8px] text-slate-400">
                                                                <span className="text-indigo-400 font-bold flex flex-col items-center">📊 Bảng giá</span>
                                                                <span className="flex flex-col items-center">📈 Biểu đồ</span>
                                                                <span className="flex flex-col items-center">🤖 AI</span>
                                                            </div>
                                                        </div>
                                                    </div>
                                                </div>

                                                {/* Content & Web Mobile Features */}
                                                <div className="space-y-4">
                                                    <div>
                                                        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 mb-2.5">
                                                            <Globe className="w-3.5 h-3.5" />
                                                            <span>Web Responsive • Không cần cài đặt</span>
                                                        </div>
                                                        <h3 className="text-lg md:text-2xl font-bold text-slate-900 dark:text-white leading-snug">
                                                            Giao diện Web tối ưu hoàn hảo cho Điện thoại
                                                        </h3>
                                                        <p className="text-xs md:text-sm text-slate-500 dark:text-slate-400 mt-1.5 leading-relaxed">
                                                            Trải nghiệm mượt mà, tốc độ phản hồi tức thời trực tiếp trên Safari, Chrome hoặc Edge di động mà không tốn dung lượng bộ nhớ.
                                                        </p>
                                                    </div>

                                                    {/* Web Mobile Highlights Grid */}
                                                    <div className="grid grid-cols-3 gap-2.5 py-1">
                                                        <div className="p-3 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200/80 dark:border-slate-800 text-center space-y-1">
                                                            <div className="w-7 h-7 rounded-lg bg-emerald-500/10 text-emerald-500 flex items-center justify-center mx-auto">
                                                                <Zap className="w-4 h-4" />
                                                            </div>
                                                            <p className="text-[11px] font-bold text-slate-800 dark:text-slate-200">0 MB Cài đặt</p>
                                                            <p className="text-[9px] text-slate-500 dark:text-slate-400">Không tốn bộ nhớ</p>
                                                        </div>
                                                        <div className="p-3 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200/80 dark:border-slate-800 text-center space-y-1">
                                                            <div className="w-7 h-7 rounded-lg bg-indigo-500/10 text-indigo-500 flex items-center justify-center mx-auto">
                                                                <Globe className="w-4 h-4" />
                                                            </div>
                                                            <p className="text-[11px] font-bold text-slate-800 dark:text-slate-200">Trực tiếp Safari/Chrome</p>
                                                            <p className="text-[9px] text-slate-500 dark:text-slate-400">Mọi thiết bị di động</p>
                                                        </div>
                                                        <div className="p-3 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200/80 dark:border-slate-800 text-center space-y-1">
                                                            <div className="w-7 h-7 rounded-lg bg-purple-500/10 text-purple-500 flex items-center justify-center mx-auto">
                                                                <Smartphone className="w-4 h-4" />
                                                            </div>
                                                            <p className="text-[11px] font-bold text-slate-800 dark:text-slate-200">PWA Toàn màn hình</p>
                                                            <p className="text-[9px] text-slate-500 dark:text-slate-400">Thêm vào màn hình chính</p>
                                                        </div>
                                                    </div>

                                                    {/* Feature Checkmarks */}
                                                    <div className="space-y-2.5 text-xs text-slate-700 dark:text-slate-300">
                                                        <div className="flex items-center gap-2.5">
                                                            <CheckCircle2 size={15} className="text-emerald-500 shrink-0" />
                                                            <span><strong>Không cần tải ứng dụng:</strong> Mở trình duyệt là dùng ngay, luôn tự động cập nhật phiên bản mới nhất.</span>
                                                        </div>
                                                        <div className="flex items-center gap-2.5">
                                                            <CheckCircle2 size={15} className="text-emerald-500 shrink-0" />
                                                            <span><strong>Bảng giá & Biểu đồ nến Realtime:</strong> Tương thích hoàn hảo với thao tác vuốt chạm trên màn hình cảm ứng.</span>
                                                        </div>
                                                        <div className="flex items-center gap-2.5">
                                                            <CheckCircle2 size={15} className="text-emerald-500 shrink-0" />
                                                            <span><strong>Đồng bộ đa nền tảng:</strong> Watchlist, danh mục và cảnh báo giá đồng bộ tức thời giữa PC và Mobile.</span>
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                        )}
                                    </motion.div>
                                )}

                                {/* 3. AMIBROKER */}
                                {active === "amibroker" && (
                                    <motion.div
                                        key="amibroker"
                                        {...fade}
                                        className="w-full space-y-5"
                                    >
                                        <div className="text-center md:text-left space-y-1">
                                            <h3 className="text-lg md:text-xl font-bold text-slate-900 dark:text-white leading-snug">
                                                Dữ liệu cho AmiBroker / MetaStock
                                            </h3>
                                            <p className="text-xs text-slate-500 dark:text-slate-400">
                                                Plugin cấp dữ liệu trực tiếp ổn định nhất cho phần mềm phân tích kỹ thuật
                                            </p>
                                        </div>

                                        {/* Stat Tiles */}
                                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                                            {[
                                                { title: "Realtime", value: "Tick-by-tick" },
                                                { title: "EOD Data", value: "Đầy đủ 3 sàn" },
                                                { title: "Intraday", value: "1m / 5m / 15m" },
                                                { title: "Lịch sử", value: "> 20 năm" },
                                            ].map((t) => (
                                                <div
                                                    key={t.title}
                                                    className="rounded-xl border border-slate-200/80 dark:border-slate-800 p-3 text-center bg-slate-50/70 dark:bg-slate-800/60"
                                                >
                                                    <p className="text-[11px] font-medium text-slate-500 dark:text-slate-400">
                                                        {t.title}
                                                    </p>
                                                    <p className="text-xs md:text-sm font-bold mt-0.5 text-indigo-600 dark:text-indigo-400">
                                                        {t.value}
                                                    </p>
                                                </div>
                                            ))}
                                        </div>

                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-5 items-center">
                                            <div className="space-y-2.5 text-xs text-slate-700 dark:text-slate-300">
                                                <div className="flex items-center gap-2">
                                                    <CheckCircle2 size={14} className="text-emerald-500 shrink-0" />
                                                    <span>Tự động cấu hình và cập nhật cơ sở dữ liệu</span>
                                                </div>
                                                <div className="flex items-center gap-2">
                                                    <CheckCircle2 size={14} className="text-emerald-500 shrink-0" />
                                                    <span>Dữ liệu điều chỉnh giá và chỉ số ngành chuẩn hóa</span>
                                                </div>
                                                <div className="flex items-center gap-2">
                                                    <CheckCircle2 size={14} className="text-emerald-500 shrink-0" />
                                                    <span>Tối ưu cho việc Backtest thuật toán giao dịch</span>
                                                </div>
                                            </div>

                                            <div className="h-[130px] rounded-xl border border-slate-200/90 dark:border-slate-800 bg-gradient-to-br from-slate-900 to-indigo-950 p-3.5 text-white flex flex-col justify-between shadow-sm">
                                                <div className="flex items-center justify-between text-xs text-indigo-300">
                                                    <span>AmiBroker Data Feed v4.2</span>
                                                    <span className="px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 text-[10px]">Connected</span>
                                                </div>
                                                <div className="flex items-center gap-3">
                                                    <Zap className="w-8 h-8 text-amber-400" />
                                                    <div>
                                                        <p className="text-xs font-bold">Tốc độ trễ &lt; 50ms</p>
                                                        <p className="text-[11px] text-slate-400">Đường truyền băng thông cao</p>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </motion.div>
                                )}

                                {/* 4. EXCEL */}
                                {active === "excel" && (
                                    <motion.div
                                        key="excel"
                                        {...fade}
                                        className="w-full"
                                    >
                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 items-center">
                                            <div className="h-[220px] rounded-2xl border border-emerald-500/30 bg-gradient-to-br from-emerald-950/20 via-slate-900 to-slate-950 p-4 text-white flex flex-col justify-between shadow-md">
                                                <div className="flex items-center gap-2">
                                                    <FileSpreadsheet className="w-5 h-5 text-emerald-400" />
                                                    <span className="text-xs font-bold text-emerald-400">Excel Financial Model</span>
                                                </div>
                                                <div className="space-y-2">
                                                    <div className="grid grid-cols-3 gap-2 text-[10px] text-slate-300 font-mono">
                                                        <div className="bg-slate-800/80 p-1.5 rounded">Ticker: VCB</div>
                                                        <div className="bg-slate-800/80 p-1.5 rounded">P/E: 12.4</div>
                                                        <div className="bg-slate-800/80 p-1.5 rounded">ROE: 21.8%</div>
                                                    </div>
                                                    <div className="h-2 rounded-full bg-emerald-500/30 w-4/5" />
                                                </div>
                                                <p className="text-[11px] text-slate-400">Tự động refresh dữ liệu tài chính qua API</p>
                                            </div>

                                            <div className="space-y-4">
                                                <div>
                                                    <h3 className="text-lg md:text-xl font-bold text-slate-900 dark:text-white leading-snug">
                                                        Khai thác dữ liệu trên Excel
                                                    </h3>
                                                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                                                        Tích hợp trực tiếp BCTC, chỉ số tài chính vào bảng tính Excel cá nhân
                                                    </p>
                                                </div>

                                                <div className="space-y-2 text-xs text-slate-700 dark:text-slate-300">
                                                    <div className="flex items-center gap-2">
                                                        <CheckCircle2 size={14} className="text-emerald-500 shrink-0" />
                                                        <span>Tích hợp PowerQuery & Pivot Table tự động</span>
                                                    </div>
                                                    <div className="flex items-center gap-2">
                                                        <CheckCircle2 size={14} className="text-emerald-500 shrink-0" />
                                                        <span>Cập nhật bảng giá realtime trong phiên giao dịch</span>
                                                    </div>
                                                    <div className="flex items-center gap-2">
                                                        <CheckCircle2 size={14} className="text-emerald-500 shrink-0" />
                                                        <span>Bộ mẫu báo cáo tài chính và định giá chuẩn sẵn dùng</span>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </motion.div>
                                )}

                                {/* 5. INFOGRAPHIC */}
                                {active === "infographic" && (
                                    <motion.div
                                        key="infographic"
                                        {...fade}
                                        className="w-full space-y-4"
                                    >
                                        <div className="text-center md:text-left space-y-1">
                                            <h3 className="text-lg md:text-xl font-bold text-slate-900 dark:text-white leading-snug">
                                                Infographic báo cáo phân tích
                                            </h3>
                                            <p className="text-xs text-slate-500 dark:text-slate-400">
                                                Tổng hợp dữ liệu ngành và doanh nghiệp qua hình ảnh trực quan, dễ hiểu
                                            </p>
                                        </div>

                                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-1">
                                            {[
                                                { title: "Báo cáo ngành Ngân hàng Q3", tag: "Ngành", time: "5 phút đọc" },
                                                { title: "Phân tích chuỗi giá trị BĐS", tag: "Doanh nghiệp", time: "7 phút đọc" },
                                                { title: "Dòng tiền khối ngoại & vĩ mô", tag: "Vĩ mô", time: "4 phút đọc" },
                                            ].map((item, i) => (
                                                <div
                                                    key={i}
                                                    className="rounded-xl overflow-hidden border border-slate-200/90 dark:border-slate-800 bg-white dark:bg-slate-900 hover:shadow-md transition-all group cursor-pointer"
                                                >
                                                    <div className="w-full h-[110px] bg-gradient-to-tr from-slate-100 to-indigo-50 dark:from-slate-800 dark:to-indigo-950/40 flex items-center justify-center p-3">
                                                        <PieChart className="w-10 h-10 text-indigo-400 group-hover:scale-110 transition-transform" />
                                                    </div>
                                                    <div className="p-3">
                                                        <span className="px-2 py-0.5 rounded-md text-[10px] font-semibold bg-indigo-500/10 text-indigo-600 dark:text-indigo-400">
                                                            {item.tag}
                                                        </span>
                                                        <p className="text-xs font-semibold text-slate-900 dark:text-white mt-1.5 line-clamp-1">
                                                            {item.title}
                                                        </p>
                                                        <p className="text-[11px] text-slate-400 dark:text-slate-500 mt-0.5">
                                                            {item.time}
                                                        </p>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    </motion.div>
                                )}

                                {/* 6. TRỢ LÝ AI */}
                                {active === "ai" && (
                                    <motion.div
                                        key="ai"
                                        {...fade}
                                        className="w-full"
                                    >
                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 items-center">
                                            {/* AI Chat Preview */}
                                            <div className="rounded-2xl border border-indigo-500/30 bg-gradient-to-b from-slate-50 to-indigo-50/20 dark:from-slate-900 dark:to-slate-950 p-4 shadow-md space-y-3">
                                                <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-2">
                                                    <div className="flex items-center gap-2">
                                                        <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                                                        <span className="text-xs font-bold text-slate-900 dark:text-white">FinSight Copilot AI</span>
                                                    </div>
                                                </div>

                                                <div className="space-y-2.5 text-xs">
                                                    <div className="max-w-[85%] rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 p-2.5 text-slate-800 dark:text-slate-200 shadow-xs">
                                                        Xin chào! Tôi là Trợ lý AI FinSight — Bạn cần phân tích mã cổ phiếu hay xu hướng ngành nào hôm nay?
                                                    </div>
                                                    <div className="ml-auto max-w-[85%] rounded-2xl bg-gradient-to-r from-indigo-600 to-purple-600 text-white p-2.5 text-right shadow-sm">
                                                        Gợi ý cổ phiếu có tín hiệu bứt phá (breakout) hôm nay?
                                                    </div>
                                                    <div className="max-w-[85%] rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 p-2.5 text-slate-800 dark:text-slate-200 shadow-xs flex items-center gap-2">
                                                        <Sparkles className="w-3.5 h-3.5 text-amber-500 shrink-0" />
                                                        <span>Mã FPT đang vượt đỉnh lịch sử với thanh khoản tăng 150%...</span>
                                                    </div>
                                                </div>
                                            </div>

                                            {/* AI Features & CTA */}
                                            <div className="space-y-4">
                                                <div>
                                                    <div className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-purple-500/10 text-purple-600 dark:text-purple-400 mb-2">
                                                        <Sparkles size={12} />
                                                        <span>Trí tuệ nhân tạo thế hệ mới</span>
                                                    </div>
                                                    <h3 className="text-lg md:text-xl font-bold text-slate-900 dark:text-white leading-snug">
                                                        Trợ lý AI cho nhà đầu tư
                                                    </h3>
                                                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                                                        Phân tích dữ liệu tài chính đa chiều, tổng hợp tin tức và giải đáp chiến lược 24/7
                                                    </p>
                                                </div>

                                                <div className="space-y-2.5 text-xs text-slate-700 dark:text-slate-300">
                                                    <div className="flex items-center gap-2">
                                                        <CheckCircle2 size={14} className="text-emerald-500 shrink-0" />
                                                        <span>Hiểu sâu thuật ngữ và bối cảnh thị trường chứng khoán VN</span>
                                                    </div>
                                                    <div className="flex items-center gap-2">
                                                        <CheckCircle2 size={14} className="text-emerald-500 shrink-0" />
                                                        <span>Truy vấn dữ liệu realtime kết hợp RAG thông minh</span>
                                                    </div>
                                                    <div className="flex items-center gap-2">
                                                        <CheckCircle2 size={14} className="text-emerald-500 shrink-0" />
                                                        <span>Tự động giải thích lý do khuyến nghị minh bạch</span>
                                                    </div>
                                                </div>

                                                {/* AI Try Now Action Button */}
                                                <div className="pt-1">
                                                    <Button
                                                        type="button"
                                                        onClick={() => {
                                                            if (typeof window !== "undefined") {
                                                                window.dispatchEvent(
                                                                    new CustomEvent("open-ai-chat", {
                                                                        detail: { prompt: "Hãy phân tích nhanh xu hướng thị trường hôm nay" },
                                                                    })
                                                                );
                                                            }
                                                        }}
                                                        className="bg-gradient-to-r from-indigo-600 via-purple-600 to-pink-600 hover:from-indigo-500 hover:via-purple-500 hover:to-pink-500 text-white text-xs font-semibold px-5 py-2.5 rounded-xl shadow-md shadow-indigo-500/25 hover:shadow-indigo-500/40 hover:-translate-y-0.5 transition-all cursor-pointer inline-flex items-center gap-1.5"
                                                    >
                                                        <Bot className="w-3.5 h-3.5" />
                                                        <span>Dùng thử ngay</span>
                                                    </Button>
                                                </div>
                                            </div>
                                        </div>
                                    </motion.div>
                                )}
                            </AnimatePresence>
                        </div>
                    </div>
                )}
            </Tabs>
        </main>
    );
}
