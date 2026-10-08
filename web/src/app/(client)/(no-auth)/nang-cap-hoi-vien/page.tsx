"use client";

import { motion } from "framer-motion";
import { Crown, ShieldCheck, CheckCircle2, Sparkles, Zap, ArrowRight, Star } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/utils/axiosInstance";
import { useAuth } from "@/auth/AuthProvider";
import { useRouter } from "next/navigation";

export default function CheckoutPremiumPage() {
    const { user } = useAuth();
    const router = useRouter();

    const handleBuy = async () => {
        if (!user) {
            router.push("/login");
            return;
        }

        const res = await api.post("/premium-orders", {
            userId: Number(user.id),
        });

        const checkoutUrl =
            res.data?.data?.payLink?.checkoutUrl || res.data?.checkoutUrl;

        if (checkoutUrl) window.location.href = checkoutUrl;
    };

    return (
        <div className="relative min-h-screen flex flex-col items-center bg-gradient-to-b from-[#f7f4ff] via-white to-[#ece8ff] dark:from-slate-950 dark:via-slate-900 dark:to-slate-950 overflow-hidden transition-colors duration-300 px-4 sm:px-6">
            {/* Ambient Background Glows */}
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_0%,rgba(147,51,234,0.12),transparent_60%)] dark:bg-[radial-gradient(circle_at_50%_0%,rgba(147,51,234,0.2),transparent_70%)] pointer-events-none" />
            <div className="absolute -left-[10rem] top-[8rem] w-[26rem] h-[26rem] bg-purple-400/20 dark:bg-purple-600/15 blur-[6rem] rounded-full pointer-events-none" />
            <div className="absolute -right-[10rem] bottom-[10rem] w-[26rem] h-[26rem] bg-blue-400/20 dark:bg-indigo-600/15 blur-[6rem] rounded-full pointer-events-none" />

            {/* Header Hero Section */}
            <motion.div
                initial={{ opacity: 0, y: 25 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6 }}
                className="mt-14 sm:mt-18 text-center relative z-10 max-w-2xl mx-auto"
            >
                <div className="inline-flex items-center gap-2 bg-purple-100/90 dark:bg-purple-950/80 border border-purple-200/80 dark:border-purple-800 text-purple-700 dark:text-purple-300 text-xs sm:text-sm font-semibold px-4 py-1.5 rounded-full mb-5 shadow-xs">
                    <Sparkles className="w-4 h-4 text-purple-600 dark:text-purple-400 animate-pulse" />
                    <span>Hội viên Độc quyền VIP</span>
                </div>

                <h1 className="text-3xl sm:text-4xl md:text-5xl font-extrabold text-slate-900 dark:text-white leading-tight tracking-tight">
                    Nâng cấp{" "}
                    <span className="bg-gradient-to-r from-purple-600 via-indigo-600 to-blue-600 dark:from-purple-400 dark:via-indigo-300 dark:to-cyan-400 bg-clip-text text-transparent">
                        FinSight Premium
                    </span>
                </h1>

                <p className="mt-4 text-base sm:text-lg text-slate-600 dark:text-slate-300 max-w-xl mx-auto leading-relaxed">
                    Mở khóa sức mạnh AI dự báo, dữ liệu tài chính chuyên sâu và khuyến nghị cổ phiếu chuẩn xác nhất.
                </p>
            </motion.div>

            {/* Pricing / Feature Card */}
            <motion.div
                initial={{ opacity: 0, y: 30 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, ease: "easeOut" }}
                className="w-full max-w-xl bg-white/90 dark:bg-slate-900/90 backdrop-blur-xl rounded-3xl shadow-2xl border border-purple-100 dark:border-slate-800 p-6 sm:p-10 mt-10 mb-16 relative z-10 transition-colors"
            >
                {/* Glow ring */}
                <div className="absolute -inset-0.5 bg-gradient-to-r from-purple-500/20 via-indigo-500/20 to-blue-500/20 rounded-3xl blur-md -z-10 dark:opacity-60" />

                {/* Crown badge */}
                <motion.div
                    initial={{ scale: 0.8, opacity: 0 }}
                    animate={{ scale: 1, opacity: 1 }}
                    transition={{ delay: 0.15 }}
                    className="flex justify-center mb-6"
                >
                    <div className="p-4 bg-gradient-to-br from-purple-100 to-indigo-100 dark:from-purple-950/80 dark:to-slate-800 rounded-2xl border border-purple-200/80 dark:border-purple-800 shadow-inner">
                        <Crown className="w-9 h-9 text-purple-600 dark:text-purple-400" />
                    </div>
                </motion.div>

                <h2 className="text-center text-2xl sm:text-3xl font-bold text-slate-900 dark:text-white mb-2">
                    Gói Hội Viên VIP Trọn Đời
                </h2>

                <p className="text-center text-slate-500 dark:text-slate-400 text-sm sm:text-base mb-8">
                    Đầu tư thông minh, đón đầu xu hướng với các công cụ tối tân nhất.
                </p>

                {/* Price Display Banner */}
                <motion.div
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: 0.2 }}
                    className="relative overflow-hidden bg-gradient-to-r from-purple-600 via-indigo-600 to-blue-600 dark:from-purple-700 dark:via-indigo-700 dark:to-blue-800 text-white rounded-2xl p-6 sm:p-8 text-center shadow-xl shadow-purple-500/20 mb-8"
                >
                    <div className="absolute top-0 right-0 transform translate-x-4 -translate-y-4 w-28 h-28 bg-white/10 rounded-full blur-xl pointer-events-none" />
                    <div className="absolute bottom-0 left-0 transform -translate-x-4 translate-y-4 w-28 h-28 bg-white/10 rounded-full blur-xl pointer-events-none" />

                    <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-white/20 backdrop-blur-md text-[11px] font-bold tracking-wider uppercase mb-3">
                        <Star className="w-3 h-3 text-amber-300 fill-amber-300" /> Ưu Đãi Đặc Biệt
                    </div>

                    <div className="text-4xl sm:text-5xl font-extrabold leading-none tracking-tight drop-shadow-sm font-mono">
                        2.000đ
                    </div>

                    <p className="text-xs sm:text-sm text-purple-100 font-medium mt-2">
                        Thanh toán một lần — Sở hữu toàn bộ tính năng trọn đời
                    </p>
                </motion.div>

                {/* Feature checklist */}
                <div className="space-y-4 mb-8">
                    {[
                        "Khuyến nghị & Điểm mua bán từ AI độ chuẩn xác cao",
                        "Trợ lý AI bóc tách & phân tích Báo cáo Tài chính (PDF)",
                        "Mở khóa toàn bộ chỉ báo kỹ thuật chuyên sâu & lọc cổ phiếu",
                        "Không giới hạn số lượt truy vấn dữ liệu và dự báo",
                        "Được ưu tiên hỗ trợ 24/7 từ đội ngũ kỹ thuật",
                    ].map((item, i) => (
                        <motion.div
                            key={i}
                            initial={{ opacity: 0, x: -15 }}
                            animate={{ opacity: 1, x: 0 }}
                            transition={{ delay: 0.25 + i * 0.08 }}
                            className="flex items-start gap-3"
                        >
                            <div className="w-5 h-5 rounded-full bg-emerald-100 dark:bg-emerald-950/80 border border-emerald-300 dark:border-emerald-700 flex items-center justify-center text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5">
                                <CheckCircle2 className="w-3.5 h-3.5" />
                            </div>
                            <p className="text-slate-700 dark:text-slate-200 text-sm sm:text-base leading-relaxed">
                                {item}
                            </p>
                        </motion.div>
                    ))}
                </div>

                {/* Action button */}
                <motion.div
                    initial={{ opacity: 0, y: 15 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.55 }}
                >
                    <Button
                        onClick={handleBuy}
                        className="w-full h-13 text-base sm:text-lg font-bold bg-gradient-to-r from-purple-600 via-indigo-600 to-indigo-700 hover:from-purple-700 hover:to-indigo-800 text-white shadow-xl shadow-indigo-500/25 hover:shadow-indigo-500/40 hover:-translate-y-0.5 transition-all duration-200 rounded-xl cursor-pointer flex items-center justify-center gap-2"
                    >
                        <span>Nâng cấp ngay</span>
                        <ArrowRight className="w-5 h-5" />
                    </Button>
                </motion.div>

                {/* Security trust badge */}
                <div className="mt-6 flex items-center justify-center gap-2 text-slate-500 dark:text-slate-400 text-xs sm:text-sm">
                    <ShieldCheck className="w-4 h-4 text-emerald-500" />
                    <span>Cổng thanh toán an toàn — Bảo mật qua PayOS</span>
                </div>
            </motion.div>

            {/* Footer note */}
            <p className="text-slate-400 dark:text-slate-500 text-xs sm:text-sm mb-8 z-10">
                © FinSight Stock — Nền tảng phân tích & dự báo chứng khoán thông minh
            </p>
        </div>
    );
}
