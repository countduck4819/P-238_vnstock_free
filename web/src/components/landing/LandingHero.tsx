"use client";

import { useState } from "react";
import Link from "next/link";
import {
    Sparkles,
    ArrowRight,
    TrendingUp,
    TrendingDown,
    Activity,
    FileText,
    CheckCircle2,
    Shield,
    BarChart3,
    Layers,
    Clock,
    Search,
    ChevronRight,
} from "lucide-react";

interface StockSample {
    ticker: string;
    name: string;
    price: string;
    change: string;
    percent: string;
    isUp: boolean;
    volume: string;
    rsi: number;
    macd: string;
    pe: string;
    roe: string;
    eps: string;
    marketCap: string;
    aiInsight: string;
    sources: { label: string; type: "report" | "technical" | "market" }[];
    chartPath: string;
    volumeBars: number[];
}

const STOCK_SAMPLES: Record<string, StockSample> = {
    VNM: {
        ticker: "VNM",
        name: "CTCP Sữa Việt Nam (Vinamilk)",
        price: "₫68,500",
        change: "+1,570",
        percent: "+2.35%",
        isUp: true,
        volume: "4.82M",
        rsi: 58.4,
        macd: "+0.42 (Bullish Crossover)",
        pe: "15.2",
        roe: "24.8%",
        eps: "₫4,520",
        marketCap: "143.2 nghìn tỷ",
        aiInsight:
            "Khối lượng giao dịch tăng +18.3% so với trung bình 20 phiên. Kết hợp cùng phân kỳ dương MACD và biên lợi nhuận ròng Q3 tăng trưởng (+14.2% YoY), tín hiệu cho thấy dòng tiền tổ chức đang tích lũy vững chắc tại ngưỡng hỗ trợ ₫68,000.",
        sources: [
            { label: "Báo cáo Q3 Trang 14", type: "report" },
            { label: "MACD Crossover", type: "technical" },
            { label: "Volume +18.3%", type: "market" },
        ],
        chartPath:
            "M 0,110 Q 50,105 100,120 T 200,90 T 300,75 T 400,60 T 500,40 T 600,25",
        volumeBars: [35, 45, 28, 55, 42, 68, 75, 52, 85, 95, 80, 100],
    },
    FPT: {
        ticker: "FPT",
        name: "CTCP FPT (FPT Corporation)",
        price: "₫138,200",
        change: "+2,500",
        percent: "+1.85%",
        isUp: true,
        volume: "3.45M",
        rsi: 64.2,
        macd: "+1.15 (Strong Momentum)",
        pe: "22.4",
        roe: "28.6%",
        eps: "₫6,180",
        marketCap: "201.8 nghìn tỷ",
        aiInsight:
            "Mảng xuất khẩu phần mềm và trung tâm dữ liệu AI ghi nhận tăng trưởng doanh thu 28.5%. Cấu trúc kỹ thuật duy trì xu hướng tăng trên đường EMA50 với lực cầu khối ngoại mua ròng 5 phiên liên tiếp.",
        sources: [
            { label: "BCTC Soát xét Q3", type: "report" },
            { label: "EMA50 Support", type: "technical" },
            { label: "Khối ngoại mua ròng", type: "market" },
        ],
        chartPath:
            "M 0,125 Q 60,110 120,95 T 240,80 T 360,65 T 480,35 T 600,15",
        volumeBars: [50, 42, 60, 55, 70, 65, 80, 88, 76, 92, 85, 98],
    },
    HPG: {
        ticker: "HPG",
        name: "CTCP Tập đoàn Hòa Phát",
        price: "₫26,400",
        change: "+200",
        percent: "+0.76%",
        isUp: true,
        volume: "18.6M",
        rsi: 52.1,
        macd: "+0.08 (Neutral-Positive)",
        pe: "12.8",
        roe: "14.2%",
        eps: "₫2,060",
        marketCap: "153.5 nghìn tỷ",
        aiInsight:
            "Tiến độ đại dự án Dung Quất 2 đạt mốc vận hành thử nghiệm giai đoạn 1. Sản lượng thép HRC phục hồi nhẹ cùng chi phí quặng sắt đầu vào hạ nhiệt, hỗ trợ biên lợi nhuận gộp hồi phục lên mức 13.6%.",
        sources: [
            { label: "Bản tin NĐT Tháng 10", type: "report" },
            { label: "Hỗ trợ MA200", type: "technical" },
            { label: "Thanh khoản 18.6M", type: "market" },
        ],
        chartPath:
            "M 0,85 Q 80,105 160,95 T 300,100 T 420,70 T 520,60 T 600,50",
        volumeBars: [60, 75, 80, 65, 90, 70, 85, 100, 78, 82, 89, 94],
    },
    VCB: {
        ticker: "VCB",
        name: "Ngân hàng TMCP Ngoại thương Việt Nam",
        price: "₫91,300",
        change: "+400",
        percent: "+0.44%",
        isUp: true,
        volume: "1.25M",
        rsi: 50.8,
        macd: "+0.12 (Consolidation)",
        pe: "14.6",
        roe: "21.5%",
        eps: "₫6,250",
        marketCap: "510.2 nghìn tỷ",
        aiInsight:
            "Tỷ lệ bao phủ nợ xấu dẫn đầu hệ thống ngân hàng (trên 230%), tỷ lệ CASA duy trì ở mức cao 35.8%. Định giá P/B hiện ở vùng trung bình 3 năm, thích hợp cho chiến lược nghiên cứu tích lũy phòng thủ.",
        sources: [
            { label: "Thuyết minh BCTC Ngân hàng", type: "report" },
            { label: "RSI Vùng Cân Bằng", type: "technical" },
            { label: "CASA 35.8%", type: "report" },
        ],
        chartPath:
            "M 0,70 Q 70,60 150,75 T 300,65 T 450,55 T 540,50 T 600,45",
        volumeBars: [40, 50, 45, 60, 55, 48, 62, 58, 65, 70, 68, 72],
    },
};

export default function LandingHero() {
    const [selectedTicker, setSelectedTicker] = useState<string>("VNM");
    const [timeframe, setTimeframe] = useState<string>("1M");
    const currentStock = STOCK_SAMPLES[selectedTicker] || STOCK_SAMPLES.VNM;

    const handleScrollToHowItWorks = (e: React.MouseEvent<HTMLAnchorElement>) => {
        e.preventDefault();
        const el = document.getElementById("how-it-works");
        if (!el) return;

        const navHeight = 84;
        const targetY = Math.max(0, el.getBoundingClientRect().top + window.scrollY - navHeight);
        const startY = window.scrollY;
        const difference = targetY - startY;
        if (Math.abs(difference) < 5) return;

        const duration = 750;
        const startTime = performance.now();
        const easeInOutCubic = (t: number) =>
            t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;

        const step = (currentTime: number) => {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);
            const ease = easeInOutCubic(progress);

            window.scrollTo(0, startY + difference * ease);

            if (progress < 1) {
                requestAnimationFrame(step);
            }
        };

        requestAnimationFrame(step);
    };

    return (
        <section className="relative pt-28 pb-16 md:pt-36 md:pb-24 overflow-hidden bg-gradient-to-b from-slate-50/80 via-white to-white">
            {/* Subtle Background Glows */}
            <div className="absolute top-10 left-1/2 -translate-x-1/2 w-[700px] h-[350px] bg-gradient-to-tr from-blue-400/10 via-indigo-400/10 to-purple-400/10 blur-[100px] pointer-events-none -z-10" />
            <div className="absolute top-40 right-10 w-[300px] h-[300px] bg-purple-300/10 blur-[80px] pointer-events-none -z-10" />

            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 lg:gap-8 items-center">
                    {/* LEFT COLUMN: Value Proposition */}
                    <div className="lg:col-span-6 space-y-6 text-center lg:text-left">
                        {/* Eyebrow badge */}
                        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-blue-50/90 border border-blue-200/80 text-blue-700 text-xs font-semibold uppercase tracking-wider shadow-sm">
                            <span className="w-2 h-2 rounded-full bg-blue-600 animate-pulse" />
                            <span>Trợ lý AI Phân tích Chứng khoán</span>
                        </div>

                        {/* Main Headline */}
                        <h1 className="text-4xl sm:text-5xl lg:text-[3.35rem] font-extrabold text-slate-900 tracking-tight leading-[1.12]">
                            Thấu hiểu thị trường. <br className="hidden sm:inline" />
                            <span className="bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 bg-clip-text text-transparent">
                                Vững tin từ Dữ liệu & AI.
                            </span>
                        </h1>

                        {/* Subheadline */}
                        <p className="text-lg sm:text-xl text-slate-600 max-w-2xl mx-auto lg:mx-0 font-normal leading-relaxed">
                            Phân tích toàn diện cổ phiếu kết hợp tín hiệu thị trường, chỉ báo kỹ thuật, báo cáo tài chính và tổng hợp AI giải thích minh bạch — tất cả trong một không gian làm việc duy nhất.
                        </p>

                        {/* CTA Action Buttons */}
                        <div className="flex flex-col sm:flex-row items-center justify-center lg:justify-start gap-3.5 pt-2">
                            <Link
                                href="/home"
                                className="w-full sm:w-auto px-7 py-3.5 text-base font-semibold text-white bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 hover:from-blue-700 hover:via-indigo-700 hover:to-purple-700 rounded-xl shadow-md hover:shadow-lg hover:shadow-blue-500/25 transition-all flex items-center justify-center gap-2 group"
                            >
                                <span>Trải nghiệm FinSight</span>
                                <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                            </Link>

                            <a
                                href="#how-it-works"
                                onClick={handleScrollToHowItWorks}
                                className="w-full sm:w-auto px-6 py-3.5 text-base font-semibold text-slate-700 bg-white hover:bg-slate-50 border border-slate-200/90 rounded-xl shadow-sm hover:border-slate-300 transition-all text-center"
                            >
                                Xem cách hoạt động
                            </a>
                        </div>

                        {/* Trust / Disclaimer line */}
                        <div className="flex items-center justify-center lg:justify-start gap-2 text-xs text-slate-500 pt-1">
                            <Shield className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                            <span>
                                Nền tảng phục vụ nghiên cứu và hỗ trợ phân tích dữ liệu. Không đưa ra khuyến nghị mua bán tùy tiện.
                            </span>
                        </div>
                    </div>

                    {/* RIGHT COLUMN: Interactive Stock-Analysis Dashboard Mockup */}
                    <div className="lg:col-span-6">
                        <div className="relative mx-auto max-w-lg lg:max-w-none bg-white rounded-2xl border border-slate-200/90 shadow-2xl shadow-slate-200/60 overflow-hidden">
                            {/* Window Top Bar / Ticker Switcher */}
                            <div className="px-4 py-3 bg-slate-50/90 border-b border-slate-200/80 flex flex-wrap items-center justify-between gap-2">
                                <div className="flex items-center gap-1.5">
                                    <span className="text-xs font-semibold text-slate-500 mr-1">Mã mẫu:</span>
                                    {Object.keys(STOCK_SAMPLES).map((tk) => (
                                        <button
                                            key={tk}
                                            onClick={() => setSelectedTicker(tk)}
                                            className={`px-2.5 py-1 text-xs font-bold rounded-md transition-all ${
                                                selectedTicker === tk
                                                    ? "bg-blue-600 text-white shadow-sm"
                                                    : "bg-white text-slate-600 hover:bg-slate-200/70 border border-slate-200"
                                            }`}
                                        >
                                            {tk}
                                        </button>
                                    ))}
                                </div>

                                <div className="flex items-center gap-1 text-[11px] font-medium text-slate-500">
                                    {["1D", "1W", "1M", "1Y"].map((tf) => (
                                        <button
                                            key={tf}
                                            onClick={() => setTimeframe(tf)}
                                            className={`px-2 py-0.5 rounded ${
                                                timeframe === tf
                                                    ? "bg-slate-200 text-slate-900 font-semibold"
                                                    : "hover:text-slate-900"
                                            }`}
                                        >
                                            {tf}
                                        </button>
                                    ))}
                                </div>
                            </div>

                            {/* Main Stock Header */}
                            <div className="p-5 pb-3">
                                <div className="flex items-start justify-between">
                                    <div>
                                        <div className="flex items-center gap-2">
                                            <span className="text-xl font-extrabold text-slate-900">
                                                {currentStock.ticker}
                                            </span>
                                            <span className="text-xs font-medium text-slate-500 truncate max-w-[200px] sm:max-w-[260px]">
                                                {currentStock.name}
                                            </span>
                                        </div>
                                        <div className="flex items-center gap-1 text-[11px] text-slate-400 mt-0.5">
                                            <Clock className="w-3 h-3" />
                                            <span>Khớp lệnh liên tục • HSX</span>
                                        </div>
                                    </div>

                                    <div className="text-right">
                                        <div className="text-2xl font-bold text-slate-900">
                                            {currentStock.price}
                                        </div>
                                        <div className="flex items-center justify-end gap-1 text-xs font-semibold text-emerald-600 mt-0.5">
                                            <TrendingUp className="w-3.5 h-3.5" />
                                            <span>
                                                {currentStock.change} ({currentStock.percent})
                                            </span>
                                        </div>
                                    </div>
                                </div>

                                {/* Simulated Interactive Chart Area */}
                                <div className="mt-4 relative bg-slate-900 rounded-xl p-4 text-white overflow-hidden shadow-inner">
                                    <div className="flex items-center justify-between text-[11px] text-slate-400 mb-2 border-b border-slate-800 pb-2">
                                        <div className="flex items-center gap-3">
                                            <span className="text-slate-200 font-semibold">Biểu đồ Kỹ thuật</span>
                                            <span className="text-emerald-400">MA20: ₫67.2</span>
                                            <span className="text-cyan-400">EMA50: ₫65.8</span>
                                        </div>
                                        <span className="text-slate-400 font-mono">Vol: {currentStock.volume}</span>
                                    </div>

                                    {/* SVG Chart Line + Gradient */}
                                    <div className="h-32 w-full relative">
                                        <svg
                                            className="w-full h-full overflow-visible"
                                            viewBox="0 0 600 140"
                                            preserveAspectRatio="none"
                                        >
                                            <defs>
                                                <linearGradient
                                                    id={`grad-${selectedTicker}`}
                                                    x1="0%"
                                                    y1="0%"
                                                    x2="0%"
                                                    y2="100%"
                                                >
                                                    <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.45" />
                                                    <stop offset="100%" stopColor="#3b82f6" stopOpacity="0.0" />
                                                </linearGradient>
                                            </defs>
                                            {/* Fill Area */}
                                            <path
                                                d={`${currentStock.chartPath} L 600,140 L 0,140 Z`}
                                                fill={`url(#grad-${selectedTicker})`}
                                            />
                                            {/* Line */}
                                            <path
                                                d={currentStock.chartPath}
                                                fill="none"
                                                stroke="#38bdf8"
                                                strokeWidth="2.5"
                                                strokeLinecap="round"
                                            />
                                        </svg>

                                        {/* Volume Bars at Bottom */}
                                        <div className="absolute bottom-0 left-0 right-0 h-8 flex items-end justify-between gap-1 opacity-60">
                                            {currentStock.volumeBars.map((height, i) => (
                                                <div
                                                    key={i}
                                                    className="flex-1 bg-emerald-500/50 hover:bg-emerald-400 transition-all rounded-t-xs"
                                                    style={{ height: `${height * 0.3}px` }}
                                                />
                                            ))}
                                        </div>
                                    </div>
                                </div>

                                {/* Technical & Fundamental Metrics Strip */}
                                <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
                                    <div className="bg-slate-50 border border-slate-200/80 rounded-lg p-2 text-center">
                                        <div className="text-[10px] text-slate-500 font-medium">RSI (14)</div>
                                        <div className="text-xs font-bold text-slate-900">{currentStock.rsi} (Neutral)</div>
                                    </div>
                                    <div className="bg-slate-50 border border-slate-200/80 rounded-lg p-2 text-center">
                                        <div className="text-[10px] text-slate-500 font-medium">MACD</div>
                                        <div className="text-xs font-bold text-emerald-600">Bullish Cross</div>
                                    </div>
                                    <div className="bg-slate-50 border border-slate-200/80 rounded-lg p-2 text-center">
                                        <div className="text-[10px] text-slate-500 font-medium">P/E & ROE</div>
                                        <div className="text-xs font-bold text-slate-900">{currentStock.pe} • {currentStock.roe}</div>
                                    </div>
                                    <div className="bg-slate-50 border border-slate-200/80 rounded-lg p-2 text-center">
                                        <div className="text-[10px] text-slate-500 font-medium">Vốn hóa</div>
                                        <div className="text-xs font-bold text-slate-900">{currentStock.marketCap}</div>
                                    </div>
                                </div>

                                {/* AI Grounded Insight Box */}
                                <div className="mt-3 p-3.5 rounded-xl bg-gradient-to-r from-blue-50/90 via-indigo-50/70 to-purple-50/90 border border-blue-200/80">
                                    <div className="flex items-center justify-between mb-1.5">
                                        <div className="flex items-center gap-1.5">
                                            <div className="w-5 h-5 rounded-md bg-gradient-to-r from-blue-600 to-purple-600 flex items-center justify-center shadow-xs">
                                                <Sparkles className="w-3 h-3 text-white" />
                                            </div>
                                            <span className="text-xs font-bold text-slate-900 tracking-tight">
                                                Stock AI Explainable Insight
                                            </span>
                                        </div>
                                        <span className="text-[10px] font-semibold text-blue-700 bg-blue-100/80 px-2 py-0.5 rounded-full">
                                            Độ tin cậy: Cao (3 Nguồn)
                                        </span>
                                    </div>

                                    <p className="text-xs text-slate-700 leading-relaxed font-normal">
                                        "{currentStock.aiInsight}"
                                    </p>

                                    {/* Evidence Pills */}
                                    <div className="mt-2.5 pt-2 border-t border-blue-200/60 flex flex-wrap items-center gap-1.5">
                                        <span className="text-[10px] font-semibold text-slate-500 mr-1">Bằng chứng:</span>
                                        {currentStock.sources.map((s, idx) => (
                                            <span
                                                key={idx}
                                                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-medium bg-white border border-blue-200 text-slate-700 shadow-2xs"
                                            >
                                                <CheckCircle2 className="w-2.5 h-2.5 text-emerald-600" />
                                                <span>{s.label}</span>
                                            </span>
                                        ))}
                                    </div>
                                </div>
                            </div>

                            {/* Card Footer Link */}
                            <div className="px-5 py-2.5 bg-slate-50 border-t border-slate-200/80 flex items-center justify-between text-xs">
                                <span className="text-slate-500">Mẫu dữ liệu thực tế thời gian thực</span>
                                <Link
                                    href={`/ma-chung-khoan/${selectedTicker.toLowerCase()}`}
                                    className="font-semibold text-blue-600 hover:text-blue-700 flex items-center gap-1 group"
                                >
                                    <span>Mở phân tích chi tiết {selectedTicker}</span>
                                    <ChevronRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
                                </Link>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </section>
    );
}
