"use client";

import { Crown, Sparkles, ArrowRight, ShieldCheck } from "lucide-react";
import Link from "next/link";

export default function UpgradeToPremium({
    activeTab,
}: {
    activeTab?: string;
}) {
    return (
        <div className="relative w-full overflow-hidden rounded-2xl border border-indigo-500/20 dark:border-indigo-500/30 bg-gradient-to-br from-indigo-50/70 via-purple-50/40 to-white dark:from-slate-900/90 dark:via-purple-950/20 dark:to-slate-900 shadow-lg shadow-indigo-500/5 transition-all">
            {/* Ambient background glow */}
            <div className="pointer-events-none absolute -top-24 left-1/2 -translate-x-1/2 w-96 h-48 bg-gradient-to-r from-indigo-500/15 via-purple-500/15 to-pink-500/15 blur-3xl" />

            <div className="relative p-8 md:p-10 text-center flex flex-col items-center gap-4">
                {/* Crown badge with glowing effect */}
                <div className="relative">
                    <div className="absolute inset-0 rounded-2xl bg-gradient-to-tr from-amber-400 to-yellow-300 blur-md opacity-40 animate-pulse" />
                    <div className="relative w-16 h-16 rounded-2xl bg-gradient-to-br from-amber-400 via-amber-500 to-yellow-500 p-0.5 shadow-md flex items-center justify-center">
                        <div className="w-full h-full rounded-[14px] bg-slate-900 flex items-center justify-center">
                            <Crown className="w-8 h-8 text-amber-400 drop-shadow-[0_0_8px_rgba(251,191,36,0.6)]" />
                        </div>
                    </div>
                </div>

                <div className="space-y-1">
                    <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-gradient-to-r from-indigo-500/10 via-purple-500/10 to-pink-500/10 text-indigo-700 dark:text-indigo-300 border border-indigo-500/20 mb-2">
                        <Sparkles className="w-3.5 h-3.5 text-indigo-500" />
                        <span>Đặc quyền Hội viên Cao cấp</span>
                    </div>

                    <h2 className="text-xl md:text-2xl font-bold bg-gradient-to-r from-slate-900 via-indigo-950 to-purple-900 dark:from-white dark:via-slate-100 dark:to-indigo-200 bg-clip-text text-transparent">
                        Tính năng dành cho thành viên Premium
                    </h2>
                </div>

                <p className="text-sm md:text-base text-slate-600 dark:text-slate-300 max-w-lg leading-relaxed">
                    {activeTab === "expert"
                        ? "Nâng cấp tài khoản Premium để truy cập toàn bộ khuyến nghị mua bán độc quyền từ các chuyên gia tài chính hàng đầu với độ chính xác cao."
                        : "Nâng cấp tài khoản Premium để mở khóa hệ thống thuật toán AI dự đoán xu hướng giá cổ phiếu với dữ liệu phân tích liên tục theo thời gian thực."}
                </p>

                {/* Feature highlights */}
                <div className="flex flex-wrap items-center justify-center gap-4 text-xs font-medium text-slate-600 dark:text-slate-400 mt-2">
                    <div className="flex items-center gap-1.5">
                        <ShieldCheck className="w-4 h-4 text-emerald-500" />
                        <span>Tín hiệu realtime</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                        <ShieldCheck className="w-4 h-4 text-emerald-500" />
                        <span>Phân tích định giá sâu</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                        <ShieldCheck className="w-4 h-4 text-emerald-500" />
                        <span>Không giới hạn mã theo dõi</span>
                    </div>
                </div>

                <Link
                    href="/nang-cap-hoi-vien"
                    className="group mt-3 inline-flex items-center gap-2 px-6 py-3 bg-gradient-to-r from-indigo-600 via-purple-600 to-pink-600 hover:from-indigo-500 hover:via-purple-500 hover:to-pink-500 text-white font-semibold text-sm rounded-xl shadow-lg shadow-indigo-500/25 hover:shadow-indigo-500/40 hover:-translate-y-0.5 transition-all duration-200"
                >
                    <span>Nâng cấp ngay</span>
                    <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                </Link>
            </div>
        </div>
    );
}
