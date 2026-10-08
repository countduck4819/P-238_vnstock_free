"use client";

import {
    Activity,
    BarChart3,
    FileSpreadsheet,
    FileText,
    Sparkles,
    CheckCircle2,
    ArrowRight,
    ArrowDown,
    Zap,
} from "lucide-react";

export default function LandingSolution() {
    const pipelineSteps = [
        {
            step: "01",
            name: "Dữ liệu thị trường",
            sub: "Market Data",
            desc: "Giá real-time, volume profile, thanh khoản khớp lệnh và lịch sử giao dịch nhiều khung thời gian.",
            icon: Activity,
            badgeColor: "bg-blue-50 text-blue-700 border-blue-200",
            iconBg: "bg-blue-600 text-white",
        },
        {
            step: "02",
            name: "Phân tích kỹ thuật",
            sub: "Technical Signals",
            desc: "RSI(14), MACD, chuỗi đường trung bình MA20/50/200, dải Bollinger và cấu trúc hỗ trợ/kháng cự.",
            icon: BarChart3,
            badgeColor: "bg-indigo-50 text-indigo-700 border-indigo-200",
            iconBg: "bg-indigo-600 text-white",
        },
        {
            step: "03",
            name: "Phân tích cơ bản",
            sub: "Fundamentals",
            desc: "Doanh thu, lợi nhuận sau thuế, biên lãi gộp, EPS, P/E, P/B, ROE và chỉ số đòn bẩy tài chính D/E.",
            icon: FileSpreadsheet,
            badgeColor: "bg-purple-50 text-purple-700 border-purple-200",
            iconBg: "bg-purple-600 text-white",
        },
        {
            step: "04",
            name: "Báo cáo tài chính",
            sub: "Financial Reports",
            desc: "Văn bản BCTC định kỳ, báo cáo thường niên, thuyết minh nợ xấu, cơ cấu tài sản & trích lập dự phòng.",
            icon: FileText,
            badgeColor: "bg-amber-50 text-amber-700 border-amber-200",
            iconBg: "bg-amber-600 text-white",
        },
        {
            step: "05",
            name: "Trí tuệ nhân tạo (RAG)",
            sub: "AI Synthesis",
            desc: "Mô hình ngôn ngữ tài chính truy xuất tài liệu chuẩn xác, tổng hợp tín hiệu và loại bỏ thiên vị cảm xúc.",
            icon: Sparkles,
            badgeColor: "bg-pink-50 text-pink-700 border-pink-200",
            iconBg: "bg-gradient-to-r from-purple-600 to-pink-600 text-white",
        },
    ];

    const handleScrollToRAG = (e: React.MouseEvent<HTMLAnchorElement>) => {
        e.preventDefault();
        const el = document.getElementById("ai-rag");
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
        <section id="solution-pipeline" className="py-20 bg-white border-b border-slate-200/80">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                {/* Section Header */}
                <div className="text-center max-w-3xl mx-auto mb-16 space-y-3">
                    <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-blue-50 border border-blue-200/80 text-blue-700 text-xs font-semibold uppercase tracking-wider">
                        <Zap className="w-3.5 h-3.5 text-blue-600" />
                        <span>Phương pháp & Giải pháp Toàn diện</span>
                    </div>

                    <h2 className="text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight">
                        Pipeline tổng hợp 5 tầng dữ liệu khoa học.
                    </h2>

                    <p className="text-slate-600 text-base sm:text-lg">
                        FinSight không phụ thuộc vào một chỉ báo đơn lẻ. Hệ thống xâu chuỗi dữ liệu theo quy trình 5 bước nghiêm ngặt để đưa ra góc nhìn khách quan nhất.
                    </p>
                </div>

                {/* 5-Step Pipeline Grid */}
                <div className="grid grid-cols-1 md:grid-cols-5 gap-4 lg:gap-5 mb-12">
                    {pipelineSteps.map((step, idx) => {
                        const Icon = step.icon;
                        return (
                            <div
                                key={step.step}
                                className="relative p-5 rounded-2xl bg-slate-50 border border-slate-200/80 hover:border-blue-400 hover:shadow-md transition-all group flex flex-col justify-between"
                            >
                                <div className="space-y-3">
                                    <div className="flex items-center justify-between">
                                        <span className="text-xs font-mono font-bold text-slate-400">
                                            BƯỚC {step.step}
                                        </span>
                                        <div
                                            className={`w-8 h-8 rounded-lg ${step.iconBg} flex items-center justify-center shadow-xs group-hover:scale-110 transition-transform`}
                                        >
                                            <Icon className="w-4 h-4" />
                                        </div>
                                    </div>

                                    <div>
                                        <h3 className="text-base font-bold text-slate-900">
                                            {step.name}
                                        </h3>
                                        <span className="text-[11px] font-medium text-slate-500">
                                            {step.sub}
                                        </span>
                                    </div>

                                    <p className="text-xs text-slate-600 leading-relaxed">
                                        {step.desc}
                                    </p>
                                </div>

                                {idx < pipelineSteps.length - 1 && (
                                    <div className="hidden md:block absolute -right-3 top-1/2 -translate-y-1/2 z-10 text-slate-300">
                                        <ArrowRight className="w-4 h-4" />
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>

                {/* Synthesis Outcome Box */}
                <div className="p-6 sm:p-8 rounded-2xl bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 text-white shadow-xl border border-slate-800">
                    <div className="flex flex-col lg:flex-row items-center justify-between gap-6">
                        <div className="space-y-2 text-center lg:text-left">
                            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 text-xs font-semibold">
                                <CheckCircle2 className="w-3.5 h-3.5" />
                                <span>Kết quả trả về cho Người dùng</span>
                            </div>
                            <h4 className="text-xl sm:text-2xl font-bold tracking-tight">
                                Nhận định Cổ phiếu Minh bạch & Khách quan
                            </h4>
                            <p className="text-sm text-slate-300 max-w-xl leading-relaxed">
                                Bạn nhận được báo cáo tóm lược ngắn gọn, kèm điểm mạnh kỹ thuật, rủi ro tài chính và liên kết trực tiếp tới trang tài liệu để bạn tự kiểm chứng bất kỳ lúc nào.
                            </p>
                        </div>

                        <a
                            href="#ai-rag"
                            onClick={handleScrollToRAG}
                            className="flex-shrink-0 px-6 py-3.5 rounded-xl bg-white text-slate-900 font-bold text-sm hover:bg-slate-100 hover:scale-[1.03] active:scale-[0.98] shadow-md transition-all flex items-center gap-2 group cursor-pointer"
                        >
                            <span>Xem mô hình RAG</span>
                            <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                        </a>
                    </div>
                </div>
            </div>
        </section>
    );
}
