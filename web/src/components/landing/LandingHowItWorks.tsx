"use client";

import { useState } from "react";
import {
    Search,
    Database,
    BarChart3,
    FileSearch,
    Sparkles,
    CheckCircle2,
    ArrowRight,
    ChevronRight,
} from "lucide-react";

export default function LandingHowItWorks() {
    const [selectedStep, setSelectedStep] = useState<number>(0);

    const steps = [
        {
            num: "01",
            title: "Select a Stock",
            vietnameseTitle: "Chọn Mã Cổ phiếu",
            desc: "Nhập mã chứng khoán (VNM, FPT, HPG, VCB...) hoặc chọn theo ngành để bắt đầu phiên phân tích.",
            icon: Search,
            detailTitle: "Khởi tạo Phiên Nghiên cứu",
            detailContent: "Hệ thống xác định mã chứng khoán, kết nối API dữ liệu sàn HSX/HNX/UPCOM và chuẩn bị cơ sở dữ liệu BCTC của doanh nghiệp.",
            tag: "Bước 1 / 5",
        },
        {
            num: "02",
            title: "Collect Market Data",
            vietnameseTitle: "Thu thập Dữ liệu Thị trường",
            desc: "Tập hợp dữ liệu giá khớp lệnh, khối lượng giao dịch, lệnh mua/bán chủ động và lịch sử biến động nhiều năm.",
            icon: Database,
            detailTitle: "Đồng bộ Dữ liệu Thời gian thực",
            detailContent: "Dữ liệu nến (OHLCV) được làm sạch, khử nhiễu và sắp xếp theo chuỗi thời gian để sẵn sàng cho các thuật toán phân tích định lượng.",
            tag: "Bước 2 / 5",
        },
        {
            num: "03",
            title: "Analyze Technical & Fundamental Signals",
            vietnameseTitle: "Tính toán Kỹ thuật & Cơ bản",
            desc: "Tự động tính toán hơn 20 chỉ báo kỹ thuật (RSI, MACD, MA) song song với hệ số định giá P/E, ROE, D/E.",
            icon: BarChart3,
            detailTitle: "Định lượng Tín hiệu Kép",
            detailContent: "Kết hợp góc nhìn định giá cơ bản (nội tại công ty) và động lượng kỹ thuật (dòng tiền giao dịch) để có cái nhìn hai chiều khách quan.",
            tag: "Bước 3 / 5",
        },
        {
            num: "04",
            title: "Retrieve Relevant Financial Info (RAG)",
            vietnameseTitle: "RAG Truy xuất Thuyết minh BCTC",
            desc: "Truy vấn các đoạn văn bản quan trọng trong báo cáo tài chính, báo cáo thường niên bằng tìm kiếm ngữ nghĩa.",
            icon: FileSearch,
            detailTitle: "Tìm kiếm Ngữ nghĩa RAG",
            detailContent: "Vector hóa toàn bộ BCTC dạng PDF. Khi phân tích, hệ thống tự động trích xuất đúng trang có thuyết minh nợ, biên lãi gộp và kế hoạch kinh doanh.",
            tag: "Bước 4 / 5",
        },
        {
            num: "05",
            title: "Generate Explainable Insights",
            vietnameseTitle: "Tạo Nhận định Minh bạch",
            desc: "AI tổng hợp dữ liệu định lượng và bằng chứng văn bản thành một báo cáo súc tích, kèm trích dẫn nguồn gốc cụ thể.",
            icon: Sparkles,
            detailTitle: "Báo cáo Tổng hợp Minh bạch",
            detailContent: "Kết luận được đưa ra kèm liên kết bằng chứng (Evidence Chain). Người dùng luôn nắm rõ lý do và nguồn dữ liệu đứng sau mỗi nhận định.",
            tag: "Bước 5 / 5",
        },
    ];

    const current = steps[selectedStep];

    return (
        <section id="how-it-works" className="py-20 bg-white border-b border-slate-200/80">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                {/* Section Header */}
                <div className="text-center max-w-3xl mx-auto mb-16 space-y-3">
                    <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-indigo-50 border border-indigo-200/80 text-indigo-700 text-xs font-semibold uppercase tracking-wider">
                        <span>Quy trình 5 bước</span>
                    </div>

                    <h2 className="text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight">
                        Từ dữ liệu tới nhận định trong vài giây.
                    </h2>

                    <p className="text-slate-600 text-base sm:text-lg">
                        Quy trình phân tích tuần tự và khoa học giúp chuyển hóa hàng triệu điểm dữ liệu thành bức tranh toàn diện dễ hiểu.
                    </p>
                </div>

                {/* Interactive 5-Step Process Switcher */}
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
                    {/* Left: Step List */}
                    <div className="lg:col-span-6 space-y-3">
                        {steps.map((step, idx) => {
                            const Icon = step.icon;
                            const isActive = selectedStep === idx;
                            return (
                                <div
                                    key={step.num}
                                    onClick={() => setSelectedStep(idx)}
                                    className={`p-4 rounded-xl border transition-all cursor-pointer flex items-start gap-4 ${isActive
                                            ? "bg-gradient-to-r from-blue-50/90 to-indigo-50/90 border-blue-400 shadow-sm"
                                            : "bg-white border-slate-200 hover:border-slate-300 hover:bg-slate-50"
                                        }`}
                                >
                                    <div
                                        className={`w-10 h-10 rounded-lg flex items-center justify-center font-bold text-sm flex-shrink-0 transition-colors ${isActive
                                                ? "bg-blue-600 text-white shadow-sm"
                                                : "bg-slate-100 text-slate-600"
                                            }`}
                                    >
                                        {step.num}
                                    </div>

                                    <div className="flex-1">
                                        <div className="flex items-center justify-between">
                                            <h3 className={`text-sm font-bold ${isActive ? "text-blue-900" : "text-slate-900"}`}>
                                                {step.title}
                                            </h3>
                                            <span className="text-[11px] font-semibold text-slate-400">
                                                {step.vietnameseTitle}
                                            </span>
                                        </div>
                                        <p className="text-xs text-slate-600 mt-1 leading-relaxed">
                                            {step.desc}
                                        </p>
                                    </div>

                                    <ChevronRight
                                        className={`w-4 h-4 mt-2 transition-transform ${isActive ? "text-blue-600 translate-x-0.5" : "text-slate-300"
                                            }`}
                                    />
                                </div>
                            );
                        })}
                    </div>

                    {/* Right: Step Deep-Dive Preview Box */}
                    <div className="lg:col-span-6 sticky top-24">
                        <div className="bg-slate-900 text-white rounded-2xl p-7 border border-slate-800 shadow-xl relative overflow-hidden">
                            <div className="absolute top-0 right-0 w-64 h-64 bg-blue-600/10 rounded-full blur-3xl pointer-events-none" />

                            <div className="relative z-10 space-y-5">
                                <div className="flex items-center justify-between border-b border-slate-800 pb-4">
                                    <div className="flex items-center gap-2">
                                        <div className="w-8 h-8 rounded-lg bg-blue-600/30 text-blue-400 border border-blue-500/40 flex items-center justify-center font-bold text-xs">
                                            {current.num}
                                        </div>
                                        <div>
                                            <div className="text-xs text-slate-400 font-semibold">{current.tag}</div>
                                            <h4 className="text-base font-bold text-white">{current.detailTitle}</h4>
                                        </div>
                                    </div>
                                    <span className="text-xs font-mono text-emerald-400 bg-emerald-950/60 border border-emerald-800 px-2.5 py-1 rounded-full">
                                        Active State
                                    </span>
                                </div>

                                <p className="text-sm text-slate-300 leading-relaxed">
                                    {current.detailContent}
                                </p>

                                {/* Visual Interactive UI Showcase (Replaces raw code box) */}
                                <div className="bg-slate-950/90 rounded-xl p-4 sm:p-5 border border-slate-800 shadow-inner">
                                    {selectedStep === 0 && (
                                        <div className="space-y-3">
                                            <div className="flex items-center justify-between bg-slate-900/90 p-3 rounded-lg border border-slate-800">
                                                <div className="flex items-center gap-2.5">
                                                    <div className="w-8 h-8 rounded-lg bg-blue-600/20 text-blue-400 flex items-center justify-center font-bold text-xs border border-blue-500/30">
                                                        VNM
                                                    </div>
                                                    <div>
                                                        <div className="text-xs font-bold text-white">CTCP Sữa Việt Nam</div>
                                                        <div className="text-[11px] text-slate-400">Sàn HOSE • Thực phẩm & Đồ uống</div>
                                                    </div>
                                                </div>
                                                <div className="text-right">
                                                    <div className="text-xs font-bold text-emerald-400">₫68,500</div>
                                                    <div className="text-[10px] text-emerald-400 font-semibold">+2.35% (Hôm nay)</div>
                                                </div>
                                            </div>

                                            <div className="grid grid-cols-3 gap-2 text-center text-xs">
                                                <div className="bg-slate-900/60 p-2.5 rounded-lg border border-slate-800/80">
                                                    <div className="text-[10px] text-slate-400">Vốn hóa</div>
                                                    <div className="font-bold text-slate-200 mt-0.5">143.2T ₫</div>
                                                </div>
                                                <div className="bg-slate-900/60 p-2.5 rounded-lg border border-slate-800/80">
                                                    <div className="text-[10px] text-slate-400">Khối lượng</div>
                                                    <div className="font-bold text-slate-200 mt-0.5">4.82M cp</div>
                                                </div>
                                                <div className="bg-slate-900/60 p-2.5 rounded-lg border border-slate-800/80">
                                                    <div className="text-[10px] text-slate-400">P/E Cơ bản</div>
                                                    <div className="font-bold text-indigo-300 mt-0.5">15.2x</div>
                                                </div>
                                            </div>

                                            <div className="flex items-center gap-2 text-[11px] text-emerald-400 bg-emerald-950/40 p-2 rounded-lg border border-emerald-900/50">
                                                <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0" />
                                                <span>Đã đồng bộ 100% dữ liệu lịch sử và BCTC 3 năm gần nhất</span>
                                            </div>
                                        </div>
                                    )}

                                    {selectedStep === 1 && (
                                        <div className="space-y-3">
                                            <div className="flex items-center justify-between text-xs pb-1 border-b border-slate-800/80">
                                                <span className="text-slate-400 font-medium">Khớp lệnh Real-time</span>
                                                <span className="flex items-center gap-1 text-[11px] text-emerald-400 font-medium">
                                                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                                                    HOSE Live Feed (12ms)
                                                </span>
                                            </div>

                                            {/* Order flow bar */}
                                            <div className="space-y-1.5">
                                                <div className="flex justify-between text-[11px] font-semibold">
                                                    <span className="text-emerald-400">Mua chủ động: 64.2% (2.95M)</span>
                                                    <span className="text-rose-400">Bán: 35.8% (1.64M)</span>
                                                </div>
                                                <div className="h-2 w-full bg-slate-800 rounded-full overflow-hidden flex">
                                                    <div className="h-full bg-emerald-500" style={{ width: "64.2%" }} />
                                                    <div className="h-full bg-rose-500" style={{ width: "35.8%" }} />
                                                </div>
                                            </div>

                                            <div className="grid grid-cols-3 gap-2 text-center text-xs pt-1">
                                                <div className="bg-slate-900/70 p-2 rounded-lg border border-slate-800/80">
                                                    <div className="text-[10px] text-slate-400">Giá Mở cửa</div>
                                                    <div className="font-bold text-slate-200">₫67,200</div>
                                                </div>
                                                <div className="bg-slate-900/70 p-2 rounded-lg border border-slate-800/80">
                                                    <div className="text-[10px] text-emerald-400">Cao nhất</div>
                                                    <div className="font-bold text-emerald-400">₫68,900</div>
                                                </div>
                                                <div className="bg-slate-900/70 p-2 rounded-lg border border-slate-800/80">
                                                    <div className="text-[10px] text-rose-400">Thấp nhất</div>
                                                    <div className="font-bold text-rose-400">₫67,000</div>
                                                </div>
                                            </div>
                                        </div>
                                    )}

                                    {selectedStep === 2 && (
                                        <div className="space-y-2.5">
                                            <div className="grid grid-cols-2 gap-2 text-xs">
                                                <div className="bg-slate-900/80 p-2.5 rounded-lg border border-slate-800 space-y-1">
                                                    <div className="flex justify-between items-center">
                                                        <span className="text-[11px] text-slate-400 font-semibold">Chỉ báo RSI (14)</span>
                                                        <span className="text-emerald-400 font-bold">58.4</span>
                                                    </div>
                                                    <div className="text-[10px] text-slate-400">Vùng xung lực tăng trưởng tốt</div>
                                                </div>
                                                <div className="bg-slate-900/80 p-2.5 rounded-lg border border-slate-800 space-y-1">
                                                    <div className="flex justify-between items-center">
                                                        <span className="text-[11px] text-slate-400 font-semibold">Chỉ báo MACD</span>
                                                        <span className="text-indigo-400 font-bold">+0.42</span>
                                                    </div>
                                                    <div className="text-[10px] text-slate-400">Golden Cross giao cắt tăng</div>
                                                </div>
                                            </div>

                                            <div className="bg-slate-900/80 p-2.5 rounded-lg border border-slate-800 flex items-center justify-between text-xs">
                                                <div>
                                                    <div className="text-[11px] text-slate-400 font-semibold">Sức khỏe Tài chính (FA)</div>
                                                    <div className="text-[10px] text-slate-300 mt-0.5">ROE: 24.8% • Biên ròng: 18.5% • Đòn bẩy D/E: 0.28x</div>
                                                </div>
                                                <span className="px-2 py-1 bg-emerald-500/20 text-emerald-300 font-bold rounded-md text-[10px]">
                                                    Rất An Toàn
                                                </span>
                                            </div>
                                        </div>
                                    )}

                                    {selectedStep === 3 && (
                                        <div className="space-y-2.5">
                                            <div className="flex items-center justify-between text-xs text-slate-400 border-b border-slate-800/80 pb-1.5">
                                                <div className="flex items-center gap-1.5">
                                                    <FileSearch className="w-3.5 h-3.5 text-purple-400" />
                                                    <span className="font-semibold text-slate-300">Truy xuất BCTC Q3/2024 (Trang 14)</span>
                                                </div>
                                                <span className="text-[10px] text-purple-300 bg-purple-950/60 px-2 py-0.5 rounded border border-purple-800/60">
                                                    Độ khớp: 99.4%
                                                </span>
                                            </div>

                                            <div className="p-3 bg-purple-950/20 border border-purple-500/30 rounded-lg text-xs leading-relaxed text-slate-200">
                                                <p className="italic text-slate-300 text-[11px]">
                                                    &ldquo;Doanh thu xuất khẩu quý này tăng +14.2% YoY; biên lãi gộp đạt 41.6% nhờ chi phí bột sữa nguyên liệu đầu vào giảm 12% so với cùng kỳ.&rdquo;
                                                </p>
                                                <div className="mt-2 flex items-center gap-2 text-[10px] text-purple-300 font-medium">
                                                    <span>Trích nguồn: Thuyết minh số 8 - Báo cáo Kiểm toán</span>
                                                </div>
                                            </div>
                                        </div>
                                    )}

                                    {selectedStep === 4 && (
                                        <div className="space-y-2.5">
                                            <div className="p-3 bg-gradient-to-r from-blue-950/40 via-indigo-950/40 to-slate-900 border border-indigo-500/30 rounded-lg text-xs space-y-2">
                                                <div className="flex items-center gap-1.5 text-indigo-300 font-bold text-xs">
                                                    <Sparkles className="w-3.5 h-3.5" />
                                                    <span>Tổng hợp Khuyến nghị AI FinSight</span>
                                                </div>
                                                <p className="text-slate-200 text-[11.5px] leading-relaxed">
                                                    Cổ phiếu VNM duy trì vùng tích lũy vững chắc tại ₫68,000. Dòng tiền chủ động áp đảo (64.2%) kết hợp biên lợi nhuận mở rộng mang lại tiềm năng tăng giá bền vững trong trung và dài hạn.
                                                </p>
                                            </div>

                                            <div className="flex flex-wrap items-center gap-1.5 text-[10px]">
                                                <span className="text-slate-400 font-medium">Bằng chứng liên kết:</span>
                                                <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">BCTC Q3 T.14</span>
                                                <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">Tín hiệu MACD Bullish</span>
                                                <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">Dòng tiền Khớp lệnh</span>
                                            </div>
                                        </div>
                                    )}
                                </div>

                                <div className="pt-2 flex items-center justify-between text-xs">
                                    <span className="text-slate-400">
                                        Tự động xử lý trong 1.8 giây
                                    </span>
                                    <button
                                        onClick={() =>
                                            setSelectedStep((prev) => (prev + 1) % steps.length)
                                        }
                                        className="text-blue-400 hover:text-blue-300 font-bold flex items-center gap-1 cursor-pointer transition-colors"
                                    >
                                        <span>Bước tiếp theo</span>
                                        <ArrowRight className="w-3.5 h-3.5" />
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </section>
    );
}
