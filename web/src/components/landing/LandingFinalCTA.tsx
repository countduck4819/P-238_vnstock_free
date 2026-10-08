"use client";

import Link from "next/link";
import { ArrowRight, Sparkles, ShieldCheck, CheckCircle2, BarChart2 } from "lucide-react";

export default function LandingFinalCTA() {
    return (
        <section className="py-20 bg-slate-900 relative overflow-hidden">
            {/* Subtle Gradient Glows */}
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[300px] bg-gradient-to-r from-blue-600/20 via-indigo-600/20 to-purple-600/20 rounded-full blur-[100px] pointer-events-none" />

            <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
                <div className="bg-gradient-to-b from-slate-800/90 to-slate-900/90 rounded-3xl p-8 sm:p-12 border border-slate-700/80 shadow-2xl text-center space-y-6">
                    {/* Badge */}
                    <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-blue-500/10 border border-blue-400/30 text-blue-300 text-xs font-semibold uppercase tracking-wider">
                        <Sparkles className="w-3.5 h-3.5" />
                        <span>Sẵn sàng nâng tầm nghiên cứu cổ phiếu?</span>
                    </div>

                    {/* Headline */}
                    <h2 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-white tracking-tight leading-tight">
                        Bắt đầu trải nghiệm phân tích cùng Trợ lý AI.
                    </h2>

                    {/* Subheadline */}
                    <p className="text-base sm:text-lg text-slate-300 max-w-2xl mx-auto font-normal leading-relaxed">
                        Hợp nhất dữ liệu thị trường, báo cáo tài chính và năng lực phân tích thông minh vào một không gian làm việc duy nhất.
                    </p>

                    {/* Action Buttons */}
                    <div className="flex flex-col sm:flex-row items-center justify-center gap-4 pt-4">
                        <Link
                            href="/home"
                            className="w-full sm:w-auto px-8 py-4 text-base font-bold text-white bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 hover:from-blue-700 hover:via-indigo-700 hover:to-purple-700 rounded-xl shadow-lg hover:shadow-blue-500/30 transition-all flex items-center justify-center gap-2 group"
                        >
                            <span>Trải nghiệm FinSight</span>
                            <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                        </Link>

                        <Link
                            href="/ma-chung-khoan/vnindex"
                            className="w-full sm:w-auto px-7 py-4 text-base font-semibold text-slate-200 bg-slate-800/80 hover:bg-slate-700 border border-slate-600 rounded-xl transition-all text-center"
                        >
                            Xem dữ liệu thị trường
                        </Link>
                    </div>

                    {/* Trust Proof Points */}
                    <div className="pt-6 border-t border-slate-700/60 flex flex-wrap items-center justify-center gap-6 text-xs text-slate-400">
                        <div className="flex items-center gap-1.5">
                            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                            <span>1,500+ Mã cổ phiếu 3 sàn</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                            <span>Dữ liệu thời gian thực</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                            <span>Minh bạch nguồn gốc dẫn chứng</span>
                        </div>
                    </div>
                </div>
            </div>
        </section>
    );
}
