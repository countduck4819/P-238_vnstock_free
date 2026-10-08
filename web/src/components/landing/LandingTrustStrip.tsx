"use client";

import {
    Activity,
    BarChart3,
    FileSpreadsheet,
    FileText,
    Sparkles,
    ShieldCheck,
} from "lucide-react";

export default function LandingTrustStrip() {
    const capabilities = [
        {
            icon: Activity,
            label: "Dữ liệu thị trường",
            desc: "HSX, HNX, UPCOM real-time",
        },
        {
            icon: BarChart3,
            label: "Phân tích kỹ thuật",
            desc: "20+ chỉ báo RSI, MACD, MA",
        },
        {
            icon: FileSpreadsheet,
            label: "Phân tích cơ bản",
            desc: "Dữ liệu tài chính 10 năm",
        },
        {
            icon: FileText,
            label: "Báo cáo tài chính",
            desc: "BCTC quý, niên độ & soát xét",
        },
        {
            icon: Sparkles,
            label: "Tổng hợp AI",
            desc: "RAG truy xuất ngữ nghĩa chuẩn",
        },
        {
            icon: ShieldCheck,
            label: "Dẫn chứng minh bạch",
            desc: "100% truy xuất nguồn gốc",
        },
    ];

    return (
        <section className="py-10 bg-slate-900 text-white border-y border-slate-800">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <div className="text-center mb-8">
                    <p className="text-xs uppercase tracking-widest text-slate-400 font-bold">
                        Hệ sinh thái phân tích tập trung
                    </p>
                    <h2 className="text-lg sm:text-xl font-bold text-white mt-1">
                        One workspace for market data, financial information and AI analysis.
                    </h2>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
                    {capabilities.map((item, idx) => {
                        const Icon = item.icon;
                        return (
                            <div
                                key={idx}
                                className="p-3.5 rounded-xl bg-slate-800/60 border border-slate-700/60 hover:border-blue-500/50 hover:bg-slate-800 transition-all duration-200 group flex flex-col items-center text-center"
                            >
                                <div className="w-9 h-9 rounded-lg bg-slate-700/80 flex items-center justify-center text-blue-400 group-hover:text-blue-300 group-hover:bg-blue-600/20 transition-all mb-2.5">
                                    <Icon className="w-4 h-4" />
                                </div>
                                <div className="font-semibold text-xs text-slate-200">
                                    {item.label}
                                </div>
                                <div className="text-[11px] text-slate-400 mt-0.5 leading-tight">
                                    {item.desc}
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>
        </section>
    );
}
