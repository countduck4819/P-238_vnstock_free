"use client";

import Link from "next/link";
import { BarChart2, Shield, Sparkles, ExternalLink, Heart } from "lucide-react";
import BrandLogo from "@/share/components/BrandLogo";

export default function LandingFooter() {
    const handleScroll = (id: string) => (e: React.MouseEvent<HTMLAnchorElement>) => {
        e.preventDefault();
        const el = document.getElementById(id);
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
        <footer className="bg-slate-950 text-slate-400 border-t border-slate-800 text-xs">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
                <div className="grid grid-cols-1 md:grid-cols-12 gap-10">
                    {/* Brand Column (4 cols) */}
                    <div className="md:col-span-4 space-y-4">
                        <Link href="/" className="flex items-center gap-2.5">
                            <BrandLogo size="md" variant="white" />
                        </Link>

                        <p className="text-slate-400 leading-relaxed text-xs max-w-sm">
                            Nền tảng nghiên cứu và phân tích chứng khoán thông minh kết hợp dữ liệu thị trường, chỉ báo kỹ thuật, báo cáo tài chính và Trợ lý AI giải thích minh bạch.
                        </p>

                        <div className="text-[11px] text-slate-500">
                            Phiên bản: FinSight AI 2.0 • Real-time Market Node
                        </div>
                    </div>

                    {/* Navigation Columns (8 cols) */}
                    <div className="md:col-span-8 grid grid-cols-2 sm:grid-cols-4 gap-6">
                        {/* Col 1 */}
                        <div className="space-y-3">
                            <div className="font-bold text-slate-200 text-xs uppercase tracking-wider">
                                Sản phẩm
                            </div>
                            <ul className="space-y-2">
                                <li>
                                    <a
                                        href="#product-showcase"
                                        onClick={handleScroll("product-showcase")}
                                        className="hover:text-white transition-colors cursor-pointer"
                                    >
                                        Tổng quan Dashboard
                                    </a>
                                </li>
                                <li>
                                    <a
                                        href="#capabilities"
                                        onClick={handleScroll("capabilities")}
                                        className="hover:text-white transition-colors cursor-pointer"
                                    >
                                        Năng lực Cốt lõi
                                    </a>
                                </li>
                                <li>
                                    <Link href="/ma-chung-khoan/vnm" className="hover:text-white transition-colors">
                                        Phân tích Cổ phiếu mẫu
                                    </Link>
                                </li>
                                <li>
                                    <Link href="/ma-chung-khoan/vnindex" className="hover:text-white transition-colors">
                                        Thị trường Real-time
                                    </Link>
                                </li>
                            </ul>
                        </div>

                        {/* Col 2 */}
                        <div className="space-y-3">
                            <div className="font-bold text-slate-200 text-xs uppercase tracking-wider">
                                Công nghệ AI
                            </div>
                            <ul className="space-y-2">
                                <li>
                                    <a
                                        href="#ai-rag"
                                        onClick={handleScroll("ai-rag")}
                                        className="hover:text-white transition-colors cursor-pointer"
                                    >
                                        Mô hình RAG Grounding
                                    </a>
                                </li>
                                <li>
                                    <a
                                        href="#explainability"
                                        onClick={handleScroll("explainability")}
                                        className="hover:text-white transition-colors cursor-pointer"
                                    >
                                        Chuỗi Bằng chứng (Evidence)
                                    </a>
                                </li>
                                <li>
                                    <a
                                        href="#how-it-works"
                                        onClick={handleScroll("how-it-works")}
                                        className="hover:text-white transition-colors cursor-pointer"
                                    >
                                        Quy trình 5 Bước
                                    </a>
                                </li>
                                <li>
                                    <a
                                        href="#capabilities"
                                        onClick={handleScroll("capabilities")}
                                        className="hover:text-white transition-colors cursor-pointer"
                                    >
                                        Đọc hiểu Thuyết minh BCTC
                                    </a>
                                </li>
                            </ul>
                        </div>

                        {/* Col 3 */}
                        <div className="space-y-3">
                            <div className="font-bold text-slate-200 text-xs uppercase tracking-wider">
                                Dữ liệu & Nguồn
                            </div>
                            <ul className="space-y-2">
                                <li>
                                    <span className="text-slate-400">Sở GDCK TP.HCM (HSX)</span>
                                </li>
                                <li>
                                    <span className="text-slate-400">Sở GDCK Hà Nội (HNX)</span>
                                </li>
                                <li>
                                    <span className="text-slate-400">Thị trường UPCoM</span>
                                </li>
                                <li>
                                    <span className="text-slate-400">BCTC Soát xét Niêm yết</span>
                                </li>
                            </ul>
                        </div>

                        {/* Col 4 */}
                        <div className="space-y-3">
                            <div className="font-bold text-slate-200 text-xs uppercase tracking-wider">
                                Pháp lý & Điều khoản
                            </div>
                            <ul className="space-y-2">
                                <li>
                                    <Link href="/privacy-policy" className="hover:text-white transition-colors">
                                        Chính sách Bảo mật
                                    </Link>
                                </li>
                                <li>
                                    <Link href="/#how-it-works" className="hover:text-white transition-colors">
                                        Về FinSight
                                    </Link>
                                </li>
                                <li>
                                    <span className="text-slate-400">Điều khoản Dịch vụ</span>
                                </li>
                                <li>
                                    <span className="text-slate-400">Liên hệ Hỗ trợ</span>
                                </li>
                            </ul>
                        </div>
                    </div>
                </div>

                {/* Mandatory Financial Disclaimer Strip (Section 21 Requirement) */}
                <div className="mt-12 pt-8 border-t border-slate-800/80 space-y-4">
                    <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 flex items-start gap-3">
                        <Shield className="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5" />
                        <div className="space-y-1">
                            <div className="font-bold text-slate-300 text-xs uppercase tracking-wider">
                                Tuyên bố Miễn trừ Trách nhiệm Tài chính (Financial Disclaimer)
                            </div>
                            <p className="text-[11px] text-slate-400 leading-relaxed">
                                Stock AI cung cấp các dữ liệu tổng hợp và nhận định phân tích với mục đích hỗ trợ nghiên cứu và tra cứu thông tin. Thông tin trên nền tảng không cấu thành lời khuyên đầu tư, khuyến nghị mua bán hay tư vấn tài chính cá nhân hóa. Mọi quyết định đầu tư trên thị trường chứng khoán cần dựa trên sự đánh giá rủi ro và nhận định độc lập của người dùng.
                            </p>
                        </div>
                    </div>

                    <div className="flex flex-col sm:flex-row items-center justify-between gap-3 text-[11px] text-slate-500 pt-2">
                        <div>
                            © {new Date().getFullYear()} FinSight Platform. Mọi quyền được bảo lưu.
                        </div>
                        <div className="flex items-center gap-4">
                            <span>DATA → ANALYSIS → AI → EXPLAINABLE INSIGHT</span>
                        </div>
                    </div>
                </div>
            </div>
        </footer>
    );
}
