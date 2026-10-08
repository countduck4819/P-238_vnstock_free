"use client";

import {
    HelpCircle,
    CheckCircle2,
    TrendingUp,
    BarChart3,
    FileText,
    Shield,
    ArrowRight,
    Search,
    Sliders,
} from "lucide-react";

export default function LandingExplainability() {
    const evidenceItems = [
        {
            category: "Thanh khoản & Khối lượng",
            metric: "Volume +18.3%",
            status: "Tích cực",
            statusColor: "text-emerald-700 bg-emerald-50 border-emerald-200",
            desc: "Khối lượng khớp 4.82M vượt trội so với trung bình 20 phiên (3.2M), xác nhận lực cầu chủ động tại vùng giá thấp.",
            source: "Sàn HSX / Khớp lệnh",
            icon: BarChart3,
        },
        {
            category: "Động lượng Kỹ thuật",
            metric: "RSI 58.4 & MACD Bullish",
            status: "Đồng thuận",
            statusColor: "text-blue-700 bg-blue-50 border-blue-200",
            desc: "Chỉ số RSI duy trì trên ngưỡng trung tính 50, đường MACD cắt lên trên Signal line tạo phân kỳ dương ngắn hạn.",
            source: "Công thức Kỹ thuật Toán học",
            icon: TrendingUp,
        },
        {
            category: "Nền tảng Tài chính",
            metric: "Lợi nhuận +12.1% YoY",
            status: "Vững vàng",
            statusColor: "text-purple-700 bg-purple-50 border-purple-200",
            desc: "Lợi nhuận sau thuế phục hồi quý thứ 3 liên tiếp, biên lợi nhuận gộp mở rộng 180 điểm cơ bản.",
            source: "Báo cáo Q3 Trang 14",
            icon: FileText,
        },
        {
            category: "Sức khỏe Nợ vay",
            metric: "Debt / Equity: 0.38",
            status: "Rủi ro thấp",
            statusColor: "text-emerald-700 bg-emerald-50 border-emerald-200",
            desc: "Tỷ lệ đòn bẩy tài chính thấp so với trung bình ngành (0.85), doanh nghiệp nắm giữ lượng tiền mặt dồi dào.",
            source: "Bảng Cân đối Kế toán",
            icon: Shield,
        },
    ];

    return (
        <section id="explainability" className="py-20 scroll-mt-16 bg-white border-b border-slate-200/80">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                {/* Section Header */}
                <div className="text-center max-w-3xl mx-auto mb-16 space-y-3">
                    <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-50 border border-emerald-200/80 text-emerald-700 text-xs font-semibold uppercase tracking-wider">
                        <Shield className="w-3.5 h-3.5 text-emerald-600" />
                        <span>Tính minh bạch tuyệt đối</span>
                    </div>

                    <h2 className="text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight">
                        Không chỉ nhận câu trả lời. <br className="hidden sm:inline" />
                        <span className="bg-gradient-to-r from-emerald-600 to-blue-600 bg-clip-text text-transparent">
                            Thấu hiểu nguồn gốc và lý do.
                        </span>
                    </h2>

                    <p className="text-slate-600 text-base sm:text-lg">
                        Các công cụ AI truyền thống thường hoạt động như chiếc "hộp đen" khó hiểu. FinSight Trợ lý AI bóc tách rõ ràng từng chuỗi bằng chứng xác thực.
                    </p>
                </div>

                {/* Split Interactive View: AI Answer vs Evidence Verification Breakdown */}
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-stretch">
                    {/* Left: AI Answer Card */}
                    <div className="lg:col-span-5 bg-gradient-to-b from-slate-50 to-white rounded-2xl p-7 border border-slate-200 shadow-sm flex flex-col justify-between">
                        <div className="space-y-4">
                            <div className="flex items-center justify-between border-b border-slate-200 pb-3">
                                <div className="text-xs font-bold uppercase tracking-wider text-slate-500">
                                    Nhận định của AI (AI Insight)
                                </div>
                                <span className="text-[10px] font-bold text-blue-700 bg-blue-100 px-2 py-0.5 rounded-full">
                                    VNM Analysis
                                </span>
                            </div>

                            <h3 className="text-xl font-bold text-slate-900 leading-snug">
                                "Cổ phiếu ghi nhận sự gia tăng đột biến về thanh khoản và dòng tiền tích lũy tại vùng hỗ trợ then chốt."
                            </h3>

                            <p className="text-xs text-slate-600 leading-relaxed">
                                AI không đưa ra khuyến nghị mua bán tùy tiện. Thay vào đó, AI đối chiếu 4 trụ cột dữ liệu độc lập để giải thích hiện tượng trên thị trường:
                            </p>

                            <div className="p-4 rounded-xl bg-blue-50/70 border border-blue-200/80 text-xs text-blue-900 space-y-2">
                                <div className="font-bold flex items-center gap-1.5">
                                    <CheckCircle2 className="w-4 h-4 text-blue-600" />
                                    <span>Tóm tắt chuỗi lập luận:</span>
                                </div>
                                <ul className="space-y-1 text-slate-700 pl-5 list-disc">
                                    <li>Lực cầu hấp thụ lượng cung giá thấp tốt.</li>
                                    <li>Động lượng RSI và MACD ủng hộ xu hướng hồi phục.</li>
                                    <li>Nền tảng tài chính lành mạnh, nợ vay thấp.</li>
                                    <li>Biên lợi nhuận gộp duy trì đà mở rộng.</li>
                                </ul>
                            </div>
                        </div>

                        <div className="pt-6 border-t border-slate-200 text-xs text-slate-500 flex items-center justify-between">
                            <span>Dẫn chứng rõ ràng 100%</span>
                            <span className="font-bold text-slate-700">4 / 4 Tiêu chí đạt chuẩn</span>
                        </div>
                    </div>

                    {/* Right: 4 Detailed Evidence Cards */}
                    <div className="lg:col-span-7 grid grid-cols-1 sm:grid-cols-2 gap-4">
                        {evidenceItems.map((item, idx) => {
                            const Icon = item.icon;
                            return (
                                <div
                                    key={idx}
                                    className="bg-white rounded-2xl p-5 border border-slate-200 hover:border-slate-300 shadow-xs hover:shadow-md transition-all flex flex-col justify-between"
                                >
                                    <div>
                                        <div className="flex items-center justify-between mb-3">
                                            <div className="w-8 h-8 rounded-lg bg-slate-100 flex items-center justify-center text-slate-700">
                                                <Icon className="w-4 h-4" />
                                            </div>
                                            <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${item.statusColor}`}>
                                                {item.status}
                                            </span>
                                        </div>

                                        <div className="text-[11px] font-semibold text-slate-400">
                                            {item.category}
                                        </div>
                                        <div className="text-base font-bold text-slate-900 my-1">
                                            {item.metric}
                                        </div>
                                        <p className="text-xs text-slate-600 leading-relaxed">
                                            {item.desc}
                                        </p>
                                    </div>

                                    <div className="mt-4 pt-3 border-t border-slate-100 text-[11px] font-medium text-slate-500 flex items-center justify-between">
                                        <span>Nguồn gốc:</span>
                                        <span className="font-semibold text-blue-700">{item.source}</span>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            </div>
        </section>
    );
}
