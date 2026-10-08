"use client";

import { useRouter } from "next/navigation";
import {
    HoverCard,
    HoverCardTrigger,
    HoverCardContent,
} from "@/components/ui/hover-card";
import {
    HelpCircle,
    BookOpen,
    LineChart,
    PieChart,
    TrendingUp,
    ArrowRight,
    Sparkles,
} from "lucide-react";

export default function InvestmentTab() {
    const router = useRouter();

    const handleSelectH120 = () => {
        window.dispatchEvent(new CustomEvent("switch-stock-tab", { detail: "h120" }));
        const targetElement = document.getElementById("stock-recommendations-section");
        if (targetElement) {
            window.history.pushState(null, "", "#h120");
            targetElement.scrollIntoView({ behavior: "smooth", block: "start" });
        } else {
            router.push("/home#h120");
        }
    };

    const handleOpenAIChat = () => {
        window.dispatchEvent(
            new CustomEvent("open-ai-chat", {
                detail: {
                    prompt: "Hãy tư vấn giúp tôi cách tối ưu hóa danh mục đầu tư, cân đối tỷ trọng các nhóm ngành và quản trị rủi ro.",
                },
            })
        );
    };

    return (
        <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 md:p-8 space-y-6 shadow-sm">
            {/* HEADER */}
            <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-100 dark:border-slate-800 pb-5">
                <div className="space-y-1">
                    <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-indigo-500/10 text-indigo-600 dark:text-indigo-400">
                        <TrendingUp size={13} />
                        <span>Công cụ Phân tích Đầu tư</span>
                    </div>
                    <h2 className="text-xl md:text-2xl font-bold bg-gradient-to-r from-indigo-600 via-purple-600 to-pink-600 bg-clip-text text-transparent">
                        Đầu tư & Quản lý Danh mục
                    </h2>
                    <p className="text-xs md:text-sm text-slate-500 dark:text-slate-400 max-w-xl">
                        Tổng hợp các công cụ định lượng và phân tích chuyên sâu hỗ trợ nhà đầu tư đưa ra quyết định tối ưu.
                    </p>
                </div>

                {/* ACTIONS */}
                <div className="flex items-center gap-3 text-xs md:text-sm font-medium text-indigo-600 dark:text-indigo-400">
                    <HoverCard>
                        <HoverCardTrigger asChild>
                            <button className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-colors cursor-pointer">
                                <HelpCircle size={15} />
                                <span>Giới thiệu</span>
                            </button>
                        </HoverCardTrigger>
                        <HoverCardContent className="w-72 text-xs shadow-xl rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-200 p-4">
                            <p className="leading-relaxed">
                                Khám phá các công cụ phân tích danh mục, xu hướng thị trường và chiến lược phân bổ vốn đa cấp độ.
                            </p>
                        </HoverCardContent>
                    </HoverCard>

                    <HoverCard>
                        <HoverCardTrigger asChild>
                            <button className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-colors cursor-pointer">
                                <BookOpen size={15} />
                                <span>Hướng dẫn</span>
                            </button>
                        </HoverCardTrigger>
                        <HoverCardContent className="w-72 text-xs shadow-xl rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-200 p-4">
                            <p className="leading-relaxed">
                                Bao gồm hướng dẫn phân bổ danh mục, quản trị rủi ro, theo dõi Sharpe Ratio và tối ưu lợi nhuận kỳ vọng.
                            </p>
                        </HoverCardContent>
                    </HoverCard>
                </div>
            </div>

            {/* FEATURE CARDS GRID */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* 1. Phân tích xu hướng & Dòng tiền -> H120 */}
                <div
                    onClick={handleSelectH120}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            handleSelectH120();
                        }
                    }}
                    className="group relative rounded-2xl p-5 border border-slate-200/80 dark:border-slate-800 bg-gradient-to-br from-slate-50/70 via-indigo-50/20 to-white dark:from-slate-900 dark:via-slate-800/50 dark:to-slate-900 shadow-sm hover:shadow-lg hover:border-indigo-500/50 hover:ring-2 hover:ring-indigo-500/20 transition-all duration-200 cursor-pointer overflow-hidden text-left"
                >
                    <div className="flex items-start gap-4">
                        <div className="p-3 rounded-xl bg-indigo-600/10 text-indigo-600 dark:text-indigo-400 border border-indigo-500/20 group-hover:scale-110 group-hover:bg-indigo-600 group-hover:text-white transition-all duration-200">
                            <LineChart size={24} />
                        </div>
                        <div className="space-y-1.5 flex-1 min-w-0">
                            <div className="flex items-center justify-between gap-2">
                                <h3 className="text-base font-bold text-slate-900 dark:text-white group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors">
                                    Phân tích xu hướng & Dòng tiền
                                </h3>
                                <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-indigo-600 dark:text-indigo-400 opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap">
                                    <span>Xem H120</span>
                                    <ArrowRight size={12} className="group-hover:translate-x-0.5 transition-transform" />
                                </span>
                            </div>
                            <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
                                Thuật toán theo dõi dòng tiền thông minh (Smart Money Flow), khối lượng tích lũy/phân phối và dự báo đảo chiều sớm với mô hình Xu hướng H120.
                            </p>
                        </div>
                    </div>
                </div>

                {/* 2. Quản lý danh mục -> AI Chat */}
                <div
                    onClick={handleOpenAIChat}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            handleOpenAIChat();
                        }
                    }}
                    className="group relative rounded-2xl p-5 border border-slate-200/80 dark:border-slate-800 bg-gradient-to-br from-slate-50/70 via-purple-50/20 to-white dark:from-slate-900 dark:via-slate-800/50 dark:to-slate-900 shadow-sm hover:shadow-lg hover:border-purple-500/50 hover:ring-2 hover:ring-purple-500/20 transition-all duration-200 cursor-pointer overflow-hidden text-left"
                >
                    <div className="flex items-start gap-4">
                        <div className="p-3 rounded-xl bg-purple-600/10 text-purple-600 dark:text-purple-400 border border-purple-500/20 group-hover:scale-110 group-hover:bg-purple-600 group-hover:text-white transition-all duration-200">
                            <PieChart size={24} />
                        </div>
                        <div className="space-y-1.5 flex-1 min-w-0">
                            <div className="flex items-center justify-between gap-2">
                                <h3 className="text-base font-bold text-slate-900 dark:text-white group-hover:text-purple-600 dark:group-hover:text-purple-400 transition-colors">
                                    Tối ưu hóa Danh mục đầu tư
                                </h3>
                                <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-purple-600 dark:text-purple-400 opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap">
                                    <span>Chat với AI</span>
                                    <Sparkles size={12} className="group-hover:scale-110 transition-transform" />
                                </span>
                            </div>
                            <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
                                Phân tích ma trận tương quan tài sản, đo lường mức độ phân tán rủi ro và nhận trợ giúp trực tiếp từ Trợ lý AI tài chính.
                            </p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
