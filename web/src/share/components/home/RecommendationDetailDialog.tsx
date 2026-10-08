"use client";

import { useMemo } from "react";
import Link from "next/link";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import {
    Clock,
    X,
    TrendingUp,
    TrendingDown,
    Target,
    ShieldAlert,
    Sparkles,
    FileText,
    Activity,
    Scale,
    Layers,
    ChevronRight,
} from "lucide-react";
import { useAppSelector } from "@/redux/hooks";
import { BadgeStatus } from "./BadgeStatus";
import { useTheme } from "@/components/theme/ThemeProvider";
import { Button } from "@/components/ui/button";
import TradingViewWidget from "@/share/components/TradingViewWidget";

export default function RecommendationDetailDialog({
    open,
    onOpenChange,
    item,
    price,
}: {
    open: boolean;
    onOpenChange: (v: boolean) => void;
    item: any;
    price: number | undefined;
}) {
    const candleData = useAppSelector((s) => s.stockSymbols.candleData);
    const { resolvedTheme } = useTheme();

    if (!item) return null;

    const symbolCode = item?.stock?.code || "VND";
    const companyName = item?.stock?.name || item?.stock?.companyName || "Công ty Cổ phần Chứng khoán";
    const exchange = item?.stock?.exchange || "HOSE";

    const latest = candleData?.[candleData.length - 1];
    const prev = candleData?.[candleData.length - 2];

    const currentClose = Number(latest?.close ?? price ?? item.buyPrice ?? 0);
    const prevClose = Number(prev?.close ?? currentClose);

    const change = currentClose - prevClose;
    const percent = prevClose ? ((change / prevClose) * 100).toFixed(2) : "0.00";

    const buyPrice = Number(item.buyPrice) || 0;
    const targetPrice = Number(item.targetPrice) || 0;
    const stopLossPrice = Number(item.stopLossPrice) || 0;

    // Potential Upside & Downside Risk
    const upsidePercent = buyPrice > 0 ? (((targetPrice - buyPrice) / buyPrice) * 100).toFixed(2) : "0.00";
    const riskPercent = buyPrice > 0 ? (((stopLossPrice - buyPrice) / buyPrice) * 100).toFixed(2) : "0.00";
    const currentReturn = buyPrice > 0 ? (((currentClose - buyPrice) / buyPrice) * 100).toFixed(2) : "0.00";

    // Risk / Reward ratio
    const reward = targetPrice - buyPrice;
    const risk = buyPrice - stopLossPrice;
    const rrRatio = risk > 0 ? (reward / risk).toFixed(2) : "2.5";

    const timeVN = new Intl.DateTimeFormat("vi-VN", {
        timeZone: "Asia/Ho_Chi_Minh",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour12: false,
    }).format(new Date());

    const handleAskAI = () => {
        window.dispatchEvent(
            new CustomEvent("open-ai-chat", {
                detail: {
                    prompt: `Hãy phân tích chi tiết khuyến nghị mã cổ phiếu ${symbolCode} (${companyName}) với giá mua ${buyPrice}, mục tiêu chốt lời ${targetPrice}, cắt lỗ ${stopLossPrice}. Nhận định xu hướng dòng tiền, hỗ trợ/kháng cự và các chỉ báo kỹ thuật hiện tại?`,
                },
            })
        );
        onOpenChange(false);
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent
                showCloseButton={false}
                className="w-[98vw] max-w-[1550px] 2xl:max-w-[1700px] max-h-[94vh] p-0 overflow-hidden bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-slate-100 rounded-3xl shadow-2xl flex flex-col"
            >
                {/* HEADER BAR */}
                <DialogHeader className="px-5 sm:px-7 py-3.5 sm:py-4 border-b border-slate-200/80 dark:border-slate-800 bg-slate-50/90 dark:bg-slate-900/95 backdrop-blur-md shrink-0 pr-12 sm:pr-14">
                    <div className="flex flex-wrap items-center justify-between gap-4">
                        {/* Left: Ticker, Name, Exchange, Time */}
                        <div className="flex items-center gap-3.5">
                            <div className="relative flex items-center justify-center w-11 h-11 sm:w-12 sm:h-12 rounded-2xl bg-gradient-to-br from-indigo-500/20 via-indigo-600/10 to-transparent dark:from-indigo-500/30 dark:via-indigo-600/20 border border-indigo-500/30 text-indigo-600 dark:text-indigo-400 font-black text-xl shadow-sm tracking-wide font-mono shrink-0">
                                {symbolCode}
                                <span className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-emerald-500 rounded-full ring-2 ring-white dark:ring-slate-900" />
                            </div>

                            <div>
                                <div className="flex items-center gap-2.5 flex-wrap">
                                    <DialogTitle className="text-base sm:text-lg font-bold text-slate-900 dark:text-white tracking-tight">
                                        {companyName}
                                    </DialogTitle>
                                    <span className="px-2 py-0.5 rounded-md text-[11px] font-bold bg-slate-200/80 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border border-slate-300/60 dark:border-slate-700">
                                        {exchange}
                                    </span>
                                    <BadgeStatus status={item.status as any} />
                                </div>

                                <div className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400 mt-1">
                                    <Clock size={13} className="text-slate-400 shrink-0" />
                                    <span>Cập nhật lúc {timeVN} | Thị trường Việt Nam (GMT+7)</span>
                                </div>
                            </div>
                        </div>

                        {/* Right: Realtime Price + Close Button */}
                        <div className="flex items-center gap-6 mr-3 sm:mr-4">
                            <div className="text-right">
                                <div className="flex items-baseline justify-end gap-1.5">
                                    <span className="text-2xl sm:text-3xl font-black text-slate-900 dark:text-white font-mono tracking-tight">
                                        {currentClose.toFixed(2)}
                                    </span>
                                    <span className="text-xs text-slate-400 font-semibold">VNĐ</span>
                                </div>
                                <div
                                    className={`inline-flex items-center gap-1 text-xs font-bold px-2 py-0.5 rounded-md mt-0.5 ${
                                        change > 0
                                            ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20"
                                            : change < 0
                                            ? "bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20"
                                            : "bg-slate-100 dark:bg-slate-800 text-slate-500"
                                    }`}
                                >
                                    {change > 0 ? <TrendingUp size={13} /> : change < 0 ? <TrendingDown size={13} /> : null}
                                    <span>
                                        {change > 0 ? "+" : ""}
                                        {change.toFixed(2)} ({percent}%)
                                    </span>
                                </div>
                            </div>

                            <button
                                onClick={() => onOpenChange(false)}
                                className="rounded-xl p-2.5 bg-slate-100 hover:bg-slate-200/80 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition-all cursor-pointer border border-slate-200/60 dark:border-slate-700"
                                title="Đóng cửa sổ"
                            >
                                <X className="h-5 w-5" />
                            </button>
                        </div>
                    </div>
                </DialogHeader>

                {/* MODAL BODY (Scrollable 2-Column Grid) */}
                <div className="flex-1 overflow-y-auto p-4 sm:p-5 lg:p-6 bg-slate-50/50 dark:bg-slate-950/60">
                    <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
                        {/* LEFT COLUMN: TradingView Interactive Candlestick Chart (Spacious 67% - 75% width) */}
                        <div className="lg:col-span-8 xl:col-span-8 2xl:col-span-9 w-full space-y-3">
                            <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm overflow-hidden">
                                <div className="px-4 py-2.5 bg-slate-100/70 dark:bg-slate-900/90 border-b border-slate-200/80 dark:border-slate-800 flex items-center justify-between text-xs flex-wrap gap-2">
                                    <div className="flex items-center gap-2 font-bold text-slate-800 dark:text-slate-200">
                                        <Activity size={15} className="text-indigo-500" />
                                        <span>Biểu đồ kỹ thuật tương tác & Dòng tiền</span>
                                    </div>
                                    <div className="flex items-center gap-2 text-[11px] text-slate-500 font-medium">
                                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-500 font-semibold">
                                            MA10 / MA50 / MA200
                                        </span>
                                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-500 font-semibold">
                                            Volume Profile
                                        </span>
                                    </div>
                                </div>

                                <div className="p-0">
                                    <TradingViewWidget
                                        symbol={symbolCode}
                                        height={530}
                                        showDrawingTools={true}
                                    />
                                </div>
                            </div>
                        </div>

                        {/* RIGHT COLUMN: Expert Target Prices, Thesis & Actions */}
                        <div className="lg:col-span-4 xl:col-span-4 2xl:col-span-3 w-full space-y-4">
                            {/* 1. KEY TARGET PRICE CARDS (3 Cards Grid) */}
                            <div className="grid grid-cols-3 gap-2.5">
                                {/* MUA */}
                                <div className="rounded-2xl border border-amber-500/30 bg-gradient-to-br from-amber-500/10 via-amber-500/5 to-transparent dark:from-amber-950/40 dark:via-slate-900 dark:to-slate-900 p-3 shadow-xs flex flex-col justify-between">
                                    <div className="flex items-center justify-between text-amber-600 dark:text-amber-400 mb-1.5">
                                        <span className="text-[11px] font-bold">Giá Mua</span>
                                        <Target size={14} />
                                    </div>
                                    <p className="text-lg sm:text-xl font-black font-mono text-slate-900 dark:text-white">
                                        {buyPrice.toFixed(2)}
                                    </p>
                                    <span className="text-[10px] text-slate-500 dark:text-slate-400 mt-1 block truncate">
                                        Giải ngân tối ưu
                                    </span>
                                </div>

                                {/* CHỐT LỜI */}
                                <div className="rounded-2xl border border-emerald-500/30 bg-gradient-to-br from-emerald-500/10 via-emerald-500/5 to-transparent dark:from-emerald-950/40 dark:via-slate-900 dark:to-slate-900 p-3 shadow-xs flex flex-col justify-between">
                                    <div className="flex items-center justify-between text-emerald-600 dark:text-emerald-400 mb-1.5">
                                        <span className="text-[11px] font-bold">Chốt Lời</span>
                                        <TrendingUp size={14} />
                                    </div>
                                    <p className="text-lg sm:text-xl font-black font-mono text-emerald-600 dark:text-emerald-400">
                                        {targetPrice.toFixed(2)}
                                    </p>
                                    <span className="text-[10px] font-bold text-emerald-600 dark:text-emerald-400 mt-1 block truncate">
                                        +{upsidePercent}% tiềm năng
                                    </span>
                                </div>

                                {/* CẮT LỖ */}
                                <div className="rounded-2xl border border-rose-500/30 bg-gradient-to-br from-rose-500/10 via-rose-500/5 to-transparent dark:from-rose-950/40 dark:via-slate-900 dark:to-slate-900 p-3 shadow-xs flex flex-col justify-between">
                                    <div className="flex items-center justify-between text-rose-600 dark:text-rose-400 mb-1.5">
                                        <span className="text-[11px] font-bold">Cắt Lỗ</span>
                                        <ShieldAlert size={14} />
                                    </div>
                                    <p className="text-lg sm:text-xl font-black font-mono text-rose-600 dark:text-rose-400">
                                        {stopLossPrice.toFixed(2)}
                                    </p>
                                    <span className="text-[10px] font-bold text-rose-600 dark:text-rose-400 mt-1 block truncate">
                                        {riskPercent}% rủi ro
                                    </span>
                                </div>
                            </div>

                            {/* 2. RISK / REWARD & PERFORMANCE STATS */}
                            <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 shadow-sm space-y-3">
                                <div className="flex items-center justify-between text-xs pb-2.5 border-b border-slate-100 dark:border-slate-800/80">
                                    <div className="flex items-center gap-2 text-slate-600 dark:text-slate-400 font-medium">
                                        <Scale size={14} className="text-indigo-500" />
                                        <span>Tỷ lệ Lợi nhuận / Rủi ro (R:R)</span>
                                    </div>
                                    <div className="flex items-center gap-1.5">
                                        <span className="font-mono font-bold text-indigo-600 dark:text-indigo-400 text-sm">
                                            1 : {rrRatio}
                                        </span>
                                        <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-indigo-500/10 text-indigo-600 dark:text-indigo-400">
                                            {Number(rrRatio) >= 2 ? "Rất hấp dẫn" : "Trung bình"}
                                        </span>
                                    </div>
                                </div>

                                <div className="flex items-center justify-between text-xs">
                                    <div className="flex items-center gap-2 text-slate-600 dark:text-slate-400 font-medium">
                                        <Layers size={14} className="text-indigo-500" />
                                        <span>Hiệu suất từ điểm mua</span>
                                    </div>
                                    <span
                                        className={`font-mono font-bold text-sm px-2 py-0.5 rounded-md ${
                                            Number(currentReturn) >= 0
                                                ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20"
                                                : "bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20"
                                        }`}
                                    >
                                        {Number(currentReturn) > 0 ? "+" : ""}
                                        {currentReturn}% {Number(currentReturn) >= 0 ? "(Đang lãi)" : "(Đang lỗ)"}
                                    </span>
                                </div>
                            </div>

                            {/* 3. INVESTMENT THESIS / DESCRIPTION */}
                            <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 sm:p-5 shadow-sm space-y-3">
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-2 text-slate-900 dark:text-white font-bold text-sm">
                                        <FileText size={16} className="text-indigo-600 dark:text-indigo-400" />
                                        <span>Luận điểm đầu tư & Phân tích</span>
                                    </div>
                                    <span className="text-[10px] font-bold uppercase tracking-wider text-indigo-600 dark:text-indigo-400 bg-indigo-500/10 px-2 py-0.5 rounded-full">
                                        Chuyên gia FinSight
                                    </span>
                                </div>
                                <div className="text-xs sm:text-sm text-slate-700 dark:text-slate-300 leading-relaxed whitespace-pre-line bg-slate-50/80 dark:bg-slate-950/70 p-3.5 rounded-xl border border-slate-200/70 dark:border-slate-800">
                                    {item.note || "Cổ phiếu đang có tín hiệu dòng tiền thông minh gia nhập, mẫu hình tích lũy chặt chẽ và triển vọng kinh doanh quý tới tăng trưởng tích cực."}
                                </div>
                            </div>

                            {/* 4. ACTION BUTTONS */}
                            <div className="space-y-2 pt-1">
                                <Button
                                    onClick={handleAskAI}
                                    className="w-full bg-gradient-to-r from-indigo-600 via-purple-600 to-pink-600 hover:from-indigo-500 hover:via-purple-500 hover:to-pink-500 text-white text-xs sm:text-sm font-bold py-3 rounded-xl shadow-lg shadow-indigo-500/25 transition-all cursor-pointer flex items-center justify-center gap-2"
                                >
                                    <Sparkles className="w-4 h-4" />
                                    <span>Hỏi Trợ lý AI FinSight về {symbolCode}</span>
                                </Button>

                                <div className="flex items-center gap-2.5">
                                    <Link
                                        href={`/ma-chung-khoan/${symbolCode}`}
                                        className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2.5 rounded-xl text-xs font-semibold bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 transition-colors border border-slate-200 dark:border-slate-700 cursor-pointer"
                                    >
                                        <span>Xem trang phân tích toàn diện</span>
                                        <ChevronRight size={14} />
                                    </Link>

                                    <Button
                                        variant="outline"
                                        onClick={() => onOpenChange(false)}
                                        className="border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 text-xs font-semibold px-4 py-2.5 rounded-xl cursor-pointer"
                                    >
                                        Đóng
                                    </Button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    );
}
