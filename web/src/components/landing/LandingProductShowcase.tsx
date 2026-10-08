"use client";

import { useState } from "react";
import Link from "next/link";
import {
    Activity,
    BarChart3,
    FileSpreadsheet,
    Sparkles,
    ArrowRight,
    TrendingUp,
    Clock,
    Search,
    Shield,
    FileText,
    ExternalLink,
    Maximize2,
} from "lucide-react";

export default function LandingProductShowcase() {
    const [activeTab, setActiveTab] = useState<"overview" | "chart" | "financials" | "ai">("overview");

    return (
        <section id="product-showcase" className="py-20 bg-slate-50 border-b border-slate-200/80">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                {/* Section Header */}
                <div className="text-center max-w-3xl mx-auto mb-12 space-y-3">
                    <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-blue-50 border border-blue-200/80 text-blue-700 text-xs font-semibold uppercase tracking-wider">
                        <Activity className="w-3.5 h-3.5 text-blue-600" />
                        <span>Trực quan hóa Giao diện</span>
                    </div>

                    <h2 className="text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight">
                        Trải nghiệm Toàn bộ Giao diện Nền tảng
                    </h2>

                    <p className="text-slate-600 text-base sm:text-lg">
                        Thiết kế với độ sâu dữ liệu mà chuyên gia đòi hỏi, kết hợp cùng sự tường minh và trợ lý AI thông minh mà người mới tiếp cận cần.
                    </p>
                </div>

                {/* Interactive Showcase Container */}
                <div className="bg-white rounded-2xl border border-slate-200 shadow-xl overflow-hidden">
                    {/* Top Navigation Tabs */}
                    <div className="px-6 py-4 bg-slate-50/90 border-b border-slate-200 flex flex-wrap items-center justify-between gap-4">
                        <div className="flex items-center gap-2">
                            <button
                                onClick={() => setActiveTab("overview")}
                                className={`px-3.5 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-2 ${activeTab === "overview"
                                        ? "bg-blue-600 text-white shadow-sm"
                                        : "bg-white text-slate-600 hover:bg-slate-200/70 border border-slate-200"
                                    }`}
                            >
                                <Activity className="w-4 h-4" />
                                <span>Tổng quan Cổ phiếu</span>
                            </button>

                            <button
                                onClick={() => setActiveTab("chart")}
                                className={`px-3.5 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-2 ${activeTab === "chart"
                                        ? "bg-blue-600 text-white shadow-sm"
                                        : "bg-white text-slate-600 hover:bg-slate-200/70 border border-slate-200"
                                    }`}
                            >
                                <BarChart3 className="w-4 h-4" />
                                <span>Biểu đồ Kỹ thuật Pro</span>
                            </button>

                            <button
                                onClick={() => setActiveTab("financials")}
                                className={`px-3.5 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-2 ${activeTab === "financials"
                                        ? "bg-blue-600 text-white shadow-sm"
                                        : "bg-white text-slate-600 hover:bg-slate-200/70 border border-slate-200"
                                    }`}
                            >
                                <FileSpreadsheet className="w-4 h-4" />
                                <span>Chỉ số Tài chính & BCTC</span>
                            </button>

                            <button
                                onClick={() => setActiveTab("ai")}
                                className={`px-3.5 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-2 ${activeTab === "ai"
                                        ? "bg-purple-600 text-white shadow-sm"
                                        : "bg-white text-purple-700 hover:bg-purple-50 border border-purple-200"
                                    }`}
                            >
                                <Sparkles className="w-4 h-4" />
                                <span>Trợ lý AI</span>
                            </button>
                        </div>

                        <Link
                            href="/home"
                            className="text-xs font-bold text-blue-600 hover:text-blue-700 flex items-center gap-1"
                        >
                            <span>Vào ứng dụng trực tiếp</span>
                            <ExternalLink className="w-3.5 h-3.5" />
                        </Link>
                    </div>

                    {/* Tab 1: Overview Showcase */}
                    {activeTab === "overview" && (
                        <div className="p-6 sm:p-8 space-y-6">
                            {/* Stock Header & Live Metrics */}
                            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-slate-100">
                                <div>
                                    <div className="flex items-center gap-3">
                                        <span className="text-2xl font-extrabold text-slate-900">VNM</span>
                                        <span className="text-sm font-semibold text-slate-600">CTCP Sữa Việt Nam (Vinamilk)</span>
                                        <span className="px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 text-xs font-bold border border-emerald-200">
                                            HSX
                                        </span>
                                    </div>
                                    <div className="text-xs text-slate-400 mt-1 flex items-center gap-2">
                                        <Clock className="w-3 h-3" /> Cập nhật lúc 15:00:00 • Giá đóng cửa phiên
                                    </div>
                                </div>

                                <div className="text-right">
                                    <div className="text-3xl font-extrabold text-slate-900">₫68,500</div>
                                    <div className="text-xs font-bold text-emerald-600 flex items-center justify-end gap-1">
                                        <TrendingUp className="w-3.5 h-3.5" /> +1,570 (+2.35%)
                                    </div>
                                </div>
                            </div>

                            {/* 3 Columns Dashboard Layout */}
                            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                                {/* Left Chart (7 cols) */}
                                <div className="lg:col-span-8 bg-slate-900 rounded-xl p-5 text-white">
                                    <div className="flex items-center justify-between text-xs text-slate-400 mb-3">
                                        <span className="font-bold text-slate-200">Biểu đồ nến Nhật & Khối lượng</span>
                                        <span className="font-mono text-emerald-400">RSI: 58.4 • MA20: ₫67.2k</span>
                                    </div>
                                    <div className="h-56 relative flex items-center justify-center border-b border-slate-800 pb-2">
                                        <svg className="w-full h-full" viewBox="0 0 500 150" preserveAspectRatio="none">
                                            <defs>
                                                <linearGradient id="showcase-grad" x1="0%" y1="0%" x2="0%" y2="100%">
                                                    <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.4" />
                                                    <stop offset="100%" stopColor="#3b82f6" stopOpacity="0.0" />
                                                </linearGradient>
                                            </defs>
                                            <path d="M 0,110 Q 50,105 100,120 T 200,90 T 300,75 T 400,60 T 500,25 L 500,150 L 0,150 Z" fill="url(#showcase-grad)" />
                                            <path d="M 0,110 Q 50,105 100,120 T 200,90 T 300,75 T 400,60 T 500,25" fill="none" stroke="#38bdf8" strokeWidth="2.5" />
                                        </svg>
                                    </div>
                                    <div className="mt-3 flex items-center justify-between text-[11px] text-slate-400">
                                        <span>Khối lượng: 4.82M cp (Cao hơn 18.3% so với 20D MA)</span>
                                        <span className="text-blue-400 font-semibold">Tín hiệu: Phân kỳ dương MACD</span>
                                    </div>
                                </div>

                                {/* Right Stats Table (4 cols) */}
                                <div className="lg:col-span-4 bg-slate-50 rounded-xl p-5 border border-slate-200 space-y-3">
                                    <div className="text-xs font-bold text-slate-900 border-b border-slate-200 pb-2">
                                        Chỉ số Định giá & Tài chính
                                    </div>

                                    <div className="space-y-2 text-xs">
                                        <div className="flex justify-between py-1 border-b border-slate-100">
                                            <span className="text-slate-500">P/E Hiện tại:</span>
                                            <span className="font-bold text-slate-900">15.2 lần</span>
                                        </div>
                                        <div className="flex justify-between py-1 border-b border-slate-100">
                                            <span className="text-slate-500">P/B:</span>
                                            <span className="font-bold text-slate-900">1.85 lần</span>
                                        </div>
                                        <div className="flex justify-between py-1 border-b border-slate-100">
                                            <span className="text-slate-500">ROE:</span>
                                            <span className="font-bold text-emerald-600">24.8%</span>
                                        </div>
                                        <div className="flex justify-between py-1 border-b border-slate-100">
                                            <span className="text-slate-500">EPS 4 Quý:</span>
                                            <span className="font-bold text-slate-900">₫4,520</span>
                                        </div>
                                        <div className="flex justify-between py-1 border-b border-slate-100">
                                            <span className="text-slate-500">Tỷ lệ Nợ/Vốn (D/E):</span>
                                            <span className="font-bold text-slate-900">0.38 (Thấp)</span>
                                        </div>
                                        <div className="flex justify-between py-1">
                                            <span className="text-slate-500">Vốn hóa Thị trường:</span>
                                            <span className="font-bold text-slate-900">143.2 nghìn tỷ</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Tab 2: Technical Chart Showcase */}
                    {activeTab === "chart" && (
                        <div className="p-6 sm:p-8 space-y-4">
                            <div className="bg-slate-900 text-white rounded-xl p-6 space-y-4">
                                <div className="flex items-center justify-between border-b border-slate-800 pb-3 text-xs">
                                    <span className="font-bold text-cyan-400">TradingView Pro Chart Engine</span>
                                    <div className="flex gap-2">
                                        <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300">MA10</span>
                                        <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300">MA50</span>
                                        <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300">MA200</span>
                                    </div>
                                </div>
                                <div className="h-64 flex items-center justify-center font-mono text-xs text-slate-400 border border-dashed border-slate-800 rounded-lg">
                                    [Tích hợp TradingView Pro: Đầy đủ công cụ vẽ Fibonacci, Hỗ trợ/Kháng cự, Volume Profile, Đa khung thời gian]
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Tab 3: Financials Showcase */}
                    {activeTab === "financials" && (
                        <div className="p-6 sm:p-8 space-y-4">
                            <div className="overflow-x-auto">
                                <table className="w-full text-xs text-left text-slate-700">
                                    <thead className="text-[11px] uppercase bg-slate-50 text-slate-500 border-b border-slate-200">
                                        <tr>
                                            <th className="py-3 px-4">Chỉ tiêu tài chính (Tỷ VNĐ)</th>
                                            <th className="py-3 px-4">Q4/2023</th>
                                            <th className="py-3 px-4">Q1/2024</th>
                                            <th className="py-3 px-4">Q2/2024</th>
                                            <th className="py-3 px-4">Q3/2024</th>
                                            <th className="py-3 px-4 text-right">Tăng trưởng YoY</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-slate-100">
                                        <tr className="hover:bg-slate-50 font-semibold">
                                            <td className="py-3 px-4">Doanh thu thuần</td>
                                            <td className="py-3 px-4">15,619</td>
                                            <td className="py-3 px-4">14,112</td>
                                            <td className="py-3 px-4">16,656</td>
                                            <td className="py-3 px-4">15,537</td>
                                            <td className="py-3 px-4 text-right text-emerald-600 font-bold">+3.8%</td>
                                        </tr>
                                        <tr className="hover:bg-slate-50">
                                            <td className="py-3 px-4">Lợi nhuận gộp</td>
                                            <td className="py-3 px-4">6,312</td>
                                            <td className="py-3 px-4">5,910</td>
                                            <td className="py-3 px-4">7,025</td>
                                            <td className="py-3 px-4">6,448</td>
                                            <td className="py-3 px-4 text-right text-emerald-600 font-bold">+8.2%</td>
                                        </tr>
                                        <tr className="hover:bg-slate-50 font-semibold">
                                            <td className="py-3 px-4">Lợi nhuận sau thuế</td>
                                            <td className="py-3 px-4">2,351</td>
                                            <td className="py-3 px-4">2,207</td>
                                            <td className="py-3 px-4">2,695</td>
                                            <td className="py-3 px-4">2,402</td>
                                            <td className="py-3 px-4 text-right text-emerald-600 font-bold">+12.1%</td>
                                        </tr>
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}

                    {/* Tab 4: Trợ lý AI Showcase */}
                    {activeTab === "ai" && (
                        <div className="p-6 sm:p-8 space-y-4">
                            <div className="p-5 rounded-xl bg-purple-50/80 border border-purple-200 text-xs text-purple-900 space-y-2">
                                <div className="flex items-center gap-2 font-bold text-sm text-purple-950">
                                    <Sparkles className="w-4 h-4 text-purple-600" />
                                    <span>Trợ lý AI Đọc hiểu & Bóc tách BCTC</span>
                                </div>
                                <p className="text-slate-700 leading-relaxed">
                                    Người dùng có thể trực tiếp đặt câu hỏi: "Phân tích rủi ro nợ vay và biến động giá vốn của VNM trong 3 quý gần nhất?" — AI sẽ đọc trực tiếp BCTC PDF và trích dẫn số trang phản hồi trong vài giây.
                                </p>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </section>
    );
}
