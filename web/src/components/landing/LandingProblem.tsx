"use client";

import { AlertCircle, Layers, FileQuestion, HelpCircle, Split, ArrowDown, Database, Cpu, CheckCircle } from "lucide-react";

export default function LandingProblem() {
    const problems = [
        {
            number: "01",
            title: "Information Overload",
            subtitle: "Quá tải dữ liệu",
            desc: "Nhà đầu tư đối mặt với hàng ngàn điểm dữ liệu giá, hàng chục chỉ báo kỹ thuật, báo cáo tài chính dài hơn 60 trang và lượng tin tức thị trường khổng lồ mỗi ngày.",
            icon: Layers,
            highlight: "Dữ liệu nhiều nhưng khó chọn lọc",
        },
        {
            number: "02",
            title: "Fragmented Information",
            subtitle: "Dữ liệu bị phân mảnh",
            desc: "Biểu đồ giá ở một công cụ, báo cáo tài chính nằm trong file PDF rời rạc, tin tức nằm ở mạng xã hội, còn phân tích định giá lại lưu trên file Excel cá nhân.",
            icon: Split,
            highlight: "Thiếu liên kết giữa Giá & Nội tại",
        },
        {
            number: "03",
            title: "Difficult Interpretation",
            subtitle: "Khó diễn giải tín hiệu",
            desc: "Sở hữu dữ liệu không đồng nghĩa với việc hiểu tín hiệu đó mang ý nghĩa gì đối với triển vọng kinh doanh, rủi ro đòn bẩy hay định giá thực tế của doanh nghiệp.",
            icon: FileQuestion,
            highlight: "Khoảng cách lớn từ Số liệu tới Hành động",
        },
    ];

    return (
        <section className="py-20 bg-slate-50 border-b border-slate-200/80">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                {/* Section Header */}
                <div className="text-center max-w-3xl mx-auto mb-16 space-y-3">
                    <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-rose-50 border border-rose-200/80 text-rose-700 text-xs font-semibold uppercase tracking-wider">
                        <AlertCircle className="w-3.5 h-3.5" />
                        <span>Thách thức của nhà đầu tư</span>
                    </div>
                    <h2 className="text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight">
                        Dữ liệu tài chính ở khắp mọi nơi. <br className="hidden sm:inline" />
                        <span className="text-rose-600">Thấu hiểu ý nghĩa mới là điều then chốt.</span>
                    </h2>
                    <p className="text-slate-600 text-base sm:text-lg">
                        Thị trường không thiếu số liệu — điều thị trường thiếu là một công cụ thông minh giúp kết nối các mảnh ghép dữ liệu rời rạc thành bức tranh rõ ràng, có căn cứ.
                    </p>
                </div>

                {/* 3 Core Problem Cards */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mb-14">
                    {problems.map((prob) => {
                        const Icon = prob.icon;
                        return (
                            <div
                                key={prob.number}
                                className="bg-white rounded-2xl p-7 border border-slate-200 shadow-sm hover:shadow-md hover:border-slate-300 transition-all relative flex flex-col justify-between group"
                            >
                                <div>
                                    <div className="flex items-center justify-between mb-5">
                                        <div className="w-12 h-12 rounded-xl bg-rose-50 text-rose-600 border border-rose-100 flex items-center justify-center font-bold text-lg group-hover:scale-105 transition-transform">
                                            <Icon className="w-6 h-6" />
                                        </div>
                                        <span className="text-xs font-mono font-bold text-slate-400 bg-slate-100 px-2.5 py-1 rounded-md">
                                            VẤN ĐỀ {prob.number}
                                        </span>
                                    </div>

                                    <h3 className="text-xl font-bold text-slate-900 mb-1">
                                        {prob.title}
                                    </h3>
                                    <div className="text-xs font-semibold text-rose-600 mb-3 uppercase tracking-wide">
                                        {prob.subtitle}
                                    </div>
                                    <p className="text-slate-600 text-sm leading-relaxed">
                                        {prob.desc}
                                    </p>
                                </div>

                                <div className="mt-6 pt-4 border-t border-slate-100 text-xs font-medium text-slate-500 flex items-center gap-1.5">
                                    <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
                                    <span>{prob.highlight}</span>
                                </div>
                            </div>
                        );
                    })}
                </div>

                {/* Visual Diagram: Multiple Fragmented Data Sources converging into Stock AI Engine */}
                <div className="bg-white rounded-2xl p-6 sm:p-8 border border-slate-200/90 shadow-sm">
                    <div className="text-center mb-6">
                        <span className="text-xs font-bold uppercase tracking-wider text-slate-400">
                            Chuyển đổi từ phân mảnh sang tập trung
                        </span>
                        <h4 className="text-base font-bold text-slate-900 mt-1">
                            Kết nối các luồng dữ liệu rời rạc thành một chuỗi nhận định có căn cứ
                        </h4>
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-center">
                        {/* Fragmented Sources */}
                        <div className="lg:col-span-5 grid grid-cols-2 gap-2.5 text-xs">
                            <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 flex items-center gap-2">
                                <span className="w-2 h-2 rounded-full bg-amber-500" />
                                <span className="font-medium text-slate-700">Dữ liệu giá & Khối lượng</span>
                            </div>
                            <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 flex items-center gap-2">
                                <span className="w-2 h-2 rounded-full bg-blue-500" />
                                <span className="font-medium text-slate-700">Chỉ báo kỹ thuật (RSI/MACD)</span>
                            </div>
                            <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 flex items-center gap-2">
                                <span className="w-2 h-2 rounded-full bg-emerald-500" />
                                <span className="font-medium text-slate-700">Báo cáo tài chính PDF</span>
                            </div>
                            <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 flex items-center gap-2">
                                <span className="w-2 h-2 rounded-full bg-purple-500" />
                                <span className="font-medium text-slate-700">Thuyết minh & Rủi ro</span>
                            </div>
                        </div>

                        {/* Convergence Arrow / Process */}
                        <div className="lg:col-span-2 flex flex-col items-center justify-center py-2 text-blue-600">
                            <div className="w-10 h-10 rounded-full bg-blue-50 border border-blue-200 flex items-center justify-center font-bold">
                                <Cpu className="w-5 h-5 animate-pulse" />
                            </div>
                            <span className="text-[11px] font-bold text-blue-700 mt-1.5 uppercase">RAG Engine</span>
                        </div>

                        {/* Unified Output */}
                        <div className="lg:col-span-5 p-4 rounded-xl bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200">
                            <div className="flex items-center gap-2 mb-1.5">
                                <CheckCircle className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                                <span className="text-xs font-bold text-slate-900">
                                    Stock AI: Báo cáo Tổng hợp Giải thích Minh bạch
                                </span>
                            </div>
                            <p className="text-xs text-slate-600 leading-relaxed">
                                Dữ liệu được trích xuất, đối chiếu chéo giữa hành vi giá và sức khỏe tài chính thực, kèm trích dẫn số trang BCTC để người dùng tự kiểm chứng.
                            </p>
                        </div>
                    </div>
                </div>
            </div>
        </section>
    );
}
