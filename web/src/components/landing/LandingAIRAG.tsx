"use client";

import { useState } from "react";
import {
    Sparkles,
    FileText,
    Database,
    ShieldCheck,
    CheckCircle2,
    Layers,
    Search,
    Cpu,
    ExternalLink,
    AlertTriangle,
} from "lucide-react";

export default function LandingAIRAG() {
    const [selectedDocPage, setSelectedDocPage] = useState<number>(14);

    return (
        <section id="ai-rag" className="py-20 scroll-mt-16 bg-slate-50 border-b border-slate-200/80">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                {/* Section Header */}
                <div className="text-center max-w-3xl mx-auto mb-16 space-y-3">
                    <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-purple-50 border border-purple-200/80 text-purple-700 text-xs font-semibold uppercase tracking-wider">
                        <Sparkles className="w-3.5 h-3.5 text-purple-600" />
                        <span>Kiến trúc RAG & AI Minh bạch</span>
                    </div>

                    <h2 className="text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight">
                        Trợ lý AI neo chặt vào dữ liệu tài chính thực tế.
                    </h2>

                    <p className="text-slate-600 text-base sm:text-lg">
                        Không sinh văn bản ngẫu nhiên hay võ đoán. Mỗi câu chữ của AI đều được neo chặt vào số liệu thực tế từ báo cáo tài chính soát xét và dữ liệu giao dịch chính thống.
                    </p>
                </div>

                {/* Visual Pipeline Flow */}
                <div className="bg-white rounded-2xl p-6 sm:p-8 border border-slate-200 shadow-sm mb-12">
                    <div className="text-xs font-bold text-slate-400 uppercase tracking-wider text-center mb-6">
                        Kiến trúc Truy xuất & Kiểm chứng Dữ liệu (RAG Architecture)
                    </div>

                    <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3 text-center">
                        <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl flex flex-col items-center">
                            <FileText className="w-5 h-5 text-blue-600 mb-1.5" />
                            <span className="text-xs font-bold text-slate-800">1. BCTC PDF</span>
                            <span className="text-[10px] text-slate-500">Báo cáo kiểm toán</span>
                        </div>

                        <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl flex flex-col items-center">
                            <Search className="w-5 h-5 text-indigo-600 mb-1.5" />
                            <span className="text-xs font-bold text-slate-800">2. Vector Search</span>
                            <span className="text-[10px] text-slate-500">Phân đoạn & Embedding</span>
                        </div>

                        <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl flex flex-col items-center">
                            <Layers className="w-5 h-5 text-purple-600 mb-1.5" />
                            <span className="text-xs font-bold text-slate-800">3. Thông tin Trọng yếu</span>
                            <span className="text-[10px] text-slate-500">Thuyết minh nợ & lãi</span>
                        </div>

                        <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl flex flex-col items-center">
                            <Database className="w-5 h-5 text-pink-600 mb-1.5" />
                            <span className="text-xs font-bold text-slate-800">4. Dữ liệu Giá Sàn</span>
                            <span className="text-[10px] text-slate-500">Thanh khoản & Khớp lệnh</span>
                        </div>

                        <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl flex flex-col items-center">
                            <Cpu className="w-5 h-5 text-amber-600 mb-1.5" />
                            <span className="text-xs font-bold text-slate-800">5. Tín hiệu Kỹ thuật</span>
                            <span className="text-[10px] text-slate-500">RSI, MACD, MA20</span>
                        </div>

                        <div className="p-3 bg-purple-50 border border-purple-200 rounded-xl flex flex-col items-center">
                            <Sparkles className="w-5 h-5 text-purple-600 mb-1.5" />
                            <span className="text-xs font-bold text-purple-900">6. AI Synthesis</span>
                            <span className="text-[10px] text-purple-700">Loại bỏ ảo giác (Hallucination)</span>
                        </div>

                        <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-xl flex flex-col items-center col-span-2 sm:col-span-1">
                            <ShieldCheck className="w-5 h-5 text-emerald-600 mb-1.5" />
                            <span className="text-xs font-bold text-emerald-900">7. Nhận định Rõ ràng</span>
                            <span className="text-[10px] text-emerald-700">Có trích dẫn 100%</span>
                        </div>
                    </div>
                </div>

                {/* Grounded AI Example Card (Comparison & Evidence Proof) */}
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
                    {/* Left: AI Insight Output */}
                    <div className="lg:col-span-7 bg-white rounded-2xl p-6 sm:p-8 border border-slate-200 shadow-sm space-y-5">
                        <div className="flex items-center justify-between border-b border-slate-100 pb-4">
                            <div className="flex items-center gap-2">
                                <div className="w-8 h-8 rounded-lg bg-gradient-to-r from-blue-600 to-purple-600 flex items-center justify-center text-white shadow-xs">
                                    <Sparkles className="w-4 h-4" />
                                </div>
                                <div>
                                    <div className="text-xs font-bold text-slate-900">Trợ lý AI Phân tích</div>
                                    <div className="text-[11px] text-slate-500">Mẫu nhận định cổ phiếu VNM</div>
                                </div>
                            </div>
                            <span className="text-xs font-bold text-emerald-700 bg-emerald-50 border border-emerald-200 px-3 py-1 rounded-full flex items-center gap-1">
                                <CheckCircle2 className="w-3.5 h-3.5" /> Bằng chứng đầy đủ
                            </span>
                        </div>

                        <div className="space-y-3 text-sm text-slate-700 leading-relaxed">
                            <p>
                                "Khối lượng giao dịch đạt <strong className="text-blue-700 font-bold bg-blue-50 px-1.5 py-0.5 rounded border border-blue-200">4.82M cổ phiếu (+18.3% so với 20D MA)</strong>, ghi nhận sự tham gia của dòng tiền lớn tại vùng giá hỗ trợ ₫68,000."
                            </p>
                            <p>
                                "Động lượng kỹ thuật đồng thuận với <strong className="text-indigo-700 font-bold bg-indigo-50 px-1.5 py-0.5 rounded border border-indigo-200">phân kỳ dương MACD (+0.42)</strong> và chỉ số RSI(14) phục hồi từ vùng 46 lên 58.4."
                            </p>
                            <p>
                                "Về nền tảng tài chính, <strong className="text-purple-700 font-bold bg-purple-50 px-1.5 py-0.5 rounded border border-purple-200">biên lợi nhuận gộp Q3 cải thiện lên 41.5%</strong> nhờ giá nguyên liệu sữa bột hạ nhiệt (chi tiết tại Thuyết minh BCTC trang 14)."
                            </p>
                        </div>

                        {/* Direct Sources Footer */}
                        <div className="pt-4 border-t border-slate-100 space-y-2">
                            <div className="text-xs font-bold text-slate-500 uppercase tracking-wider">
                                Nguồn trích xuất (Sources & Citations):
                            </div>
                            <div className="flex flex-wrap gap-2">
                                <button
                                    onClick={() => setSelectedDocPage(14)}
                                    className="px-3 py-1.5 rounded-lg bg-slate-50 hover:bg-slate-100 border border-slate-200 text-xs font-semibold text-slate-700 flex items-center gap-1.5 transition-colors"
                                >
                                    <FileText className="w-3.5 h-3.5 text-purple-600" />
                                    <span>Báo cáo Q3 Trang 14 (Thuyết minh Giá vốn)</span>
                                </button>
                                <div className="px-3 py-1.5 rounded-lg bg-slate-50 border border-slate-200 text-xs font-semibold text-slate-700 flex items-center gap-1.5">
                                    <Database className="w-3.5 h-3.5 text-blue-600" />
                                    <span>Dữ liệu khớp lệnh sàn HSX</span>
                                </div>
                                <div className="px-3 py-1.5 rounded-lg bg-slate-50 border border-slate-200 text-xs font-semibold text-slate-700 flex items-center gap-1.5">
                                    <Layers className="w-3.5 h-3.5 text-indigo-600" />
                                    <span>Chỉ báo MACD & RSI(14)</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Right: Simulated Document Excerpt Verification Viewer */}
                    <div className="lg:col-span-5 bg-slate-900 text-white rounded-2xl p-6 sm:p-7 border border-slate-800 shadow-xl space-y-4">
                        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                            <div className="flex items-center gap-2">
                                <FileText className="w-4 h-4 text-purple-400" />
                                <span className="text-xs font-bold font-mono text-slate-300">
                                    BCTC_Q3_VNM_SOAT_XET.PDF
                                </span>
                            </div>
                            <span className="text-[11px] font-mono text-slate-400 bg-slate-800 px-2 py-0.5 rounded">
                                Trang {selectedDocPage} / 48
                            </span>
                        </div>

                        <div className="bg-slate-950 rounded-xl p-4 border border-slate-800/80 font-mono text-xs text-slate-300 space-y-3 leading-relaxed">
                            <div className="text-[10px] text-purple-400 uppercase tracking-widest border-b border-slate-800 pb-1">
                                Đoạn trích dẫn được AI neo ngữ nghĩa (Chunk #184):
                            </div>
                            <p className="bg-purple-950/40 p-2.5 rounded-lg border border-purple-700/50 text-slate-200">
                                "...Trong kỳ kế toán Q3, giá vốn hàng bán giảm 3.2% so với cùng kỳ năm trước chủ yếu do chi phí nguyên vật liệu sữa đầu vào giảm trên thị trường quốc tế, góp phần nâng <span className="text-emerald-400 font-bold">biên lợi nhuận gộp lên 41.5%</span> (so với 39.7% cùng kỳ)..."
                            </p>
                            <div className="text-[11px] text-slate-400">
                                ✓ Khớp đối chiếu: <span className="text-emerald-400 font-semibold">100% chính xác</span> với nhận định AI.
                            </div>
                        </div>

                        <div className="text-xs text-slate-400 pt-2 flex items-center justify-between">
                            <span>Không lo hallucination</span>
                            <span className="text-purple-400 font-semibold">AI + Evidence + Explanation</span>
                        </div>
                    </div>
                </div>
            </div>
        </section>
    );
}
