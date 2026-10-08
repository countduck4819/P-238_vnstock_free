"use client";

import { Check, X, Sparkles, Layers, ShieldCheck } from "lucide-react";

export default function LandingDifferentiation() {
    const comparisonRows = [
        {
            feature: "Dữ liệu thị trường & Giá khớp lệnh Real-time",
            traditional: true,
            genericAi: false,
            stockAi: true,
        },
        {
            feature: "Biểu đồ kỹ thuật chuyên sâu (RSI, MACD, MA)",
            traditional: true,
            genericAi: false,
            stockAi: true,
        },
        {
            feature: "Số liệu tài chính 10 năm & BCTC định kỳ",
            traditional: true,
            genericAi: "Hạn chế",
            stockAi: true,
        },
        {
            feature: "RAG Đọc hiểu thuyết minh BCTC dạng PDF",
            traditional: false,
            genericAi: "Không đồng bộ",
            stockAi: true,
        },
        {
            feature: "Tổng hợp nhận định bằng ngôn ngữ tự nhiên",
            traditional: false,
            genericAi: true,
            stockAi: true,
        },
        {
            feature: "Chuỗi bằng chứng minh bạch (Explainable Citations)",
            traditional: false,
            genericAi: false,
            stockAi: true,
        },
        {
            feature: "Thiết kế thân thiện cho cả người mới & chuyên gia",
            traditional: false,
            genericAi: true,
            stockAi: true,
        },
    ];

    return (
        <section className="py-20 bg-white border-b border-slate-200/80">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                {/* Section Header */}
                <div className="text-center max-w-3xl mx-auto mb-16 space-y-3">
                    <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-blue-50 border border-blue-200/80 text-blue-700 text-xs font-semibold uppercase tracking-wider">
                        <Layers className="w-3.5 h-3.5 text-blue-600" />
                        <span>Sự khác biệt vượt trội</span>
                    </div>

                    <h2 className="text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight">
                        Vượt xa một bảng giá chứng khoán thông thường.
                    </h2>

                    <p className="text-slate-600 text-base sm:text-lg">
                        Không chỉ hiển thị số liệu khô khan, FinSight Trợ lý AI mang tới góc nhìn toàn cảnh nơi mọi tín hiệu đều được giải thích rõ ràng.
                    </p>
                </div>

                {/* Comparison Matrix Table */}
                <div className="max-w-4xl mx-auto bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
                    <div className="overflow-x-auto">
                        <table className="w-full text-left text-xs sm:text-sm">
                            <thead className="bg-slate-50 border-b border-slate-200 text-slate-700">
                                <tr>
                                    <th className="py-4 px-6 font-bold">Tính năng Phân tích</th>
                                    <th className="py-4 px-4 font-semibold text-center text-slate-500">
                                        Bảng giá truyền thống
                                    </th>
                                    <th className="py-4 px-4 font-semibold text-center text-slate-500">
                                        Chatbot AI thông thường
                                    </th>
                                    <th className="py-4 px-6 font-bold text-center text-blue-700 bg-blue-50/70 border-x border-blue-200">
                                        <div className="flex items-center justify-center gap-1.5">
                                            <Sparkles className="w-4 h-4 text-blue-600" />
                                            <span>FinSight Trợ lý AI</span>
                                        </div>
                                    </th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100 text-slate-600">
                                {comparisonRows.map((row, idx) => (
                                    <tr key={idx} className="hover:bg-slate-50/70 transition-colors">
                                        <td className="py-3.5 px-6 font-medium text-slate-900">
                                            {row.feature}
                                        </td>
                                        <td className="py-3.5 px-4 text-center">
                                            {row.traditional === true ? (
                                                <Check className="w-4 h-4 text-emerald-600 mx-auto" />
                                            ) : row.traditional === false ? (
                                                <X className="w-4 h-4 text-slate-300 mx-auto" />
                                            ) : (
                                                <span className="text-xs text-slate-500">{row.traditional}</span>
                                            )}
                                        </td>
                                        <td className="py-3.5 px-4 text-center">
                                            {row.genericAi === true ? (
                                                <Check className="w-4 h-4 text-emerald-600 mx-auto" />
                                            ) : row.genericAi === false ? (
                                                <X className="w-4 h-4 text-slate-300 mx-auto" />
                                            ) : (
                                                <span className="text-xs text-amber-600 font-semibold">{row.genericAi}</span>
                                            )}
                                        </td>
                                        <td className="py-3.5 px-6 text-center bg-blue-50/40 border-x border-blue-100 font-bold text-blue-900">
                                            <Check className="w-5 h-5 text-blue-600 mx-auto" />
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>

                    <div className="p-4 bg-slate-50 border-t border-slate-200 text-center text-xs font-semibold text-slate-700">
                        "Một không gian duy nhất để thấu hiểu trọn vẹn bức tranh thị trường."
                    </div>
                </div>
            </div>
        </section>
    );
}
