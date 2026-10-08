"use client";

import { useState } from "react";
import {
    Activity,
    BarChart3,
    FileSpreadsheet,
    Sparkles,
    TrendingUp,
    CheckCircle2,
    Sliders,
    Search,
    Layers,
    FileText,
    ArrowUpRight,
} from "lucide-react";

export default function LandingCapabilities() {
    const [activeCard, setActiveCard] = useState<number>(0);

    const capabilities = [
        {
            id: "market",
            title: "Market Intelligence",
            vietnameseTitle: "Dữ liệu Thị trường Thông minh",
            description: "Thấu hiểu diễn biến thực tế của cổ phiếu thông qua dòng tiền khớp lệnh, biên độ giá và thanh khoản trực tiếp từ 3 sàn giao dịch.",
            icon: Activity,
            iconColor: "text-blue-600 bg-blue-50 border-blue-200",
            features: [
                "Biến động giá Real-time (Khớp lệnh từng giây)",
                "Khối lượng giao dịch & Hồ sơ thanh khoản (Volume Profile)",
                "Lịch sử giá đa khung thời gian (1D, 1W, 1M, 1Y)",
                "Bản đồ nhiệt dòng tiền theo ngành & Khối ngoại",
            ],
            demoSnippet: {
                title: "Thanh khoản & Giá trị giao dịch",
                stat1: "Khối lượng: 12.4M cp",
                stat2: "Giá trị: ₫328.5 tỷ",
                badge: "Biên độ: +2.8%",
            },
        },
        {
            id: "technical",
            title: "Technical Analysis",
            vietnameseTitle: "Phân tích Kỹ thuật Chuyên sâu",
            description: "Khám phá các tín hiệu định lượng giúp giải thích động lượng thị trường, vùng quá mua/quá bán và các điểm hội tụ xu hướng.",
            icon: BarChart3,
            iconColor: "text-indigo-600 bg-indigo-50 border-indigo-200",
            features: [
                "Chỉ báo động lượng RSI(14), Stochastic & MFI",
                "Chỉ báo xu hướng MACD, Bollinger Bands, Parabolic SAR",
                "Chuỗi đường trung bình động MA20, EMA50, MA200",
                "Tự động phát hiện phân kỳ dương / phân kỳ âm",
            ],
            demoSnippet: {
                title: "Tín hiệu Kỹ thuật Tự động",
                stat1: "RSI(14): 58.4 (Tích lũy)",
                stat2: "MACD: Phân kỳ dương (+0.42)",
                badge: "Xu hướng: Tăng ngắn hạn",
            },
        },
        {
            id: "fundamental",
            title: "Fundamental Analysis",
            vietnameseTitle: "Phân tích Cơ bản & BCTC",
            description: "Đánh giá nội tại kinh doanh thực chất, chất lượng tài sản và sức khỏe dòng tiền thông qua hệ thống chỉ số tài chính chuẩn tắc.",
            icon: FileSpreadsheet,
            iconColor: "text-purple-600 bg-purple-50 border-purple-200",
            features: [
                "Biểu đồ tăng trưởng Doanh thu & Lợi nhuận sau thuế 5 năm",
                "Chỉ tiêu định giá P/E, P/B, EV/EBITDA so với trung bình ngành",
                "Hiệu quả sinh lời ROE, ROA, ROCE và biên lợi nhuận gộp",
                "Cấu trúc vốn: Tỷ lệ nợ vay trên vốn chủ sở hữu (D/E)",
            ],
            demoSnippet: {
                title: "Chỉ tiêu Tài chính Cốt lõi",
                stat1: "P/E: 15.2 • P/B: 1.85",
                stat2: "ROE: 24.8% • Biên gộp: 41.2%",
                badge: "Tài chính: Lành mạnh",
            },
        },
        {
            id: "ai",
            title: "AI-Powered Insights",
            vietnameseTitle: "Tổng hợp Thông minh từ AI & RAG",
            description: "Biến hàng trăm trang báo cáo và hàng triệu dòng số liệu phức tạp thành nhận định cô đọng, mạch lạc và có thể kiểm chứng.",
            icon: Sparkles,
            iconColor: "text-pink-600 bg-pink-50 border-pink-200",
            features: [
                "Diễn giải lý do thị trường biến động bằng ngôn ngữ tự nhiên",
                "RAG truy xuất tự động thuyết minh báo cáo tài chính mới nhất",
                "Cảnh báo rủi ro đòn bẩy, lưu chuyển tiền thuần và dòng tiền âm",
                "Trích dẫn số trang và dẫn chứng tài liệu cụ thể 100%",
            ],
            demoSnippet: {
                title: "Trích dẫn Bằng chứng AI",
                stat1: "Trích từ: BCTC Q3 Trang 14",
                stat2: "Độ tin cậy: 98% (Đối chiếu chéo)",
                badge: "Explainable AI",
            },
        },
    ];

    return (
        <section id="capabilities" className="py-20 bg-slate-50 border-b border-slate-200/80">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                {/* Section Header */}
                <div className="text-center max-w-3xl mx-auto mb-16 space-y-3">
                    <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-blue-50 border border-blue-200/80 text-blue-700 text-xs font-semibold uppercase tracking-wider">
                        <Sliders className="w-3.5 h-3.5 text-blue-600" />
                        <span>Năng lực Cốt lõi</span>
                    </div>

                    <h2 className="text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight">
                        Năng lực Toàn diện Cho Nghiên cứu Đầu tư
                    </h2>

                    <p className="text-slate-600 text-base sm:text-lg">
                        Mỗi tính năng được thiết kế để giải quyết trọn vẹn một khía cạnh trong quy trình phân tích đầu tư bài bản.
                    </p>
                </div>

                {/* 4 Feature Cards (2x2 Grid) */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                    {capabilities.map((cap, index) => {
                        const Icon = cap.icon;
                        return (
                            <div
                                key={cap.id}
                                onMouseEnter={() => setActiveCard(index)}
                                className={`bg-white rounded-2xl p-7 sm:p-8 border transition-all duration-300 relative flex flex-col justify-between shadow-sm hover:shadow-xl ${activeCard === index
                                        ? "border-blue-400 ring-2 ring-blue-100"
                                        : "border-slate-200 hover:border-slate-300"
                                    }`}
                            >
                                <div>
                                    {/* Card Header */}
                                    <div className="flex items-center justify-between mb-5">
                                        <div className={`w-12 h-12 rounded-xl border ${cap.iconColor} flex items-center justify-center`}>
                                            <Icon className="w-6 h-6" />
                                        </div>
                                        <span className="text-xs font-mono font-bold text-slate-400 bg-slate-100 px-2.5 py-1 rounded-md">
                                            0{index + 1}
                                        </span>
                                    </div>

                                    {/* Titles */}
                                    <h3 className="text-xl font-bold text-slate-900 mb-1">
                                        {cap.title}
                                    </h3>
                                    <div className="text-xs font-semibold text-blue-600 mb-3">
                                        {cap.vietnameseTitle}
                                    </div>

                                    <p className="text-sm text-slate-600 leading-relaxed mb-6">
                                        {cap.description}
                                    </p>

                                    {/* Bullet Features */}
                                    <div className="space-y-2.5 mb-6">
                                        {cap.features.map((feat, fIdx) => (
                                            <div key={fIdx} className="flex items-start gap-2 text-xs text-slate-700">
                                                <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0 mt-0.5" />
                                                <span>{feat}</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>

                                {/* Mini Demo Snippet Pill */}
                                <div className="mt-4 pt-4 border-t border-slate-100 bg-slate-50/90 rounded-xl p-3.5 border border-slate-200/80">
                                    <div className="flex items-center justify-between text-xs font-semibold text-slate-900 mb-1.5">
                                        <span>{cap.demoSnippet.title}</span>
                                        <span className="text-[10px] font-bold text-blue-700 bg-blue-100/80 px-2 py-0.5 rounded-full">
                                            {cap.demoSnippet.badge}
                                        </span>
                                    </div>
                                    <div className="flex items-center justify-between text-xs text-slate-600">
                                        <span>{cap.demoSnippet.stat1}</span>
                                        <span className="font-mono text-slate-500">{cap.demoSnippet.stat2}</span>
                                    </div>
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>
        </section>
    );
}
