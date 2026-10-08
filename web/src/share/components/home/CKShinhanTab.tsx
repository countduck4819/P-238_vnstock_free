"use client";

import { Info, BookOpen, TrendingUp, ShieldCheck, Zap, Globe, Award } from "lucide-react";
import {
    HoverCard,
    HoverCardTrigger,
    HoverCardContent,
} from "@/components/ui/hover-card";

export default function CKShinhanTab() {
    return (
        <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 md:p-8 space-y-6 shadow-sm">
            {/* HEADER */}
            <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-100 dark:border-slate-800 pb-5">
                <div className="space-y-1">
                    <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-blue-500/10 text-blue-600 dark:text-blue-400">
                        <Globe size={13} />
                        <span>Đối tác Chiến lược</span>
                    </div>
                    <h2 className="text-xl md:text-2xl font-bold bg-gradient-to-r from-blue-600 via-indigo-600 to-cyan-600 bg-clip-text text-transparent">
                        Chứng Khoán Shinhan (SSV)
                    </h2>
                    <p className="text-xs md:text-sm text-slate-500 dark:text-slate-400 max-w-xl">
                        Nền tảng chứng khoán thuộc tập đoàn tài chính Shinhan Financial Group – Top đầu Hàn Quốc và Châu Á.
                    </p>
                </div>

                {/* ACTIONS */}
                <div className="flex items-center gap-3 text-xs md:text-sm font-medium text-blue-600 dark:text-blue-400">
                    <HoverCard>
                        <HoverCardTrigger asChild>
                            <button className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-950/40 transition-colors cursor-pointer">
                                <Info size={15} />
                                <span>Giới thiệu</span>
                            </button>
                        </HoverCardTrigger>
                        <HoverCardContent className="w-72 text-xs shadow-xl rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-200 p-4">
                            <p className="leading-relaxed">
                                Shinhan Securities Vietnam (SSV) mang đến nền tảng giao dịch tốc độ cao, phí ưu đãi và tiêu chuẩn bảo mật ngân hàng Hàn Quốc.
                            </p>
                        </HoverCardContent>
                    </HoverCard>

                    <HoverCard>
                        <HoverCardTrigger asChild>
                            <button className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-950/40 transition-colors cursor-pointer">
                                <BookOpen size={15} />
                                <span>Hướng dẫn</span>
                            </button>
                        </HoverCardTrigger>
                        <HoverCardContent className="w-72 text-xs shadow-xl rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-200 p-4">
                            <p className="leading-relaxed">
                                Hướng dẫn mở tài khoản eKYC chỉ trong 3 phút, nạp/rút tiền liên ngân hàng 24/7 và kết nối dữ liệu cùng FinSight.
                            </p>
                        </HoverCardContent>
                    </HoverCard>
                </div>
            </div>

            {/* INFO CARD */}
            <div className="rounded-2xl p-6 border border-blue-500/20 dark:border-blue-500/30 bg-gradient-to-br from-blue-50/60 via-indigo-50/20 to-white dark:from-slate-900 dark:via-blue-950/20 dark:to-slate-900 shadow-sm">
                <div className="flex items-start gap-4">
                    <div className="p-3 rounded-xl bg-blue-600/10 text-blue-600 dark:text-blue-400 border border-blue-500/20 shrink-0">
                        <Award size={26} />
                    </div>

                    <div className="space-y-3 flex-1">
                        <h3 className="text-base font-bold text-slate-900 dark:text-white">
                            Ưu điểm nổi bật khi giao dịch tại SSV
                        </h3>

                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs text-slate-700 dark:text-slate-300">
                            <div className="flex items-center gap-2">
                                <Zap className="w-4 h-4 text-blue-500 shrink-0" />
                                <span>Phí giao dịch cạnh tranh & miễn phí mở tài khoản</span>
                            </div>
                            <div className="flex items-center gap-2">
                                <ShieldCheck className="w-4 h-4 text-emerald-500 shrink-0" />
                                <span>Hệ thống bảo mật đa lớp chuẩn tài chính quốc tế</span>
                            </div>
                            <div className="flex items-center gap-2">
                                <TrendingUp className="w-4 h-4 text-indigo-500 shrink-0" />
                                <span>Báo cáo chiến lược vĩ mô và doanh nghiệp chuyên sâu</span>
                            </div>
                            <div className="flex items-center gap-2">
                                <Globe className="w-4 h-4 text-cyan-500 shrink-0" />
                                <span>Kết nối trực tiếp hệ sinh thái tập đoàn Shinhan</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
