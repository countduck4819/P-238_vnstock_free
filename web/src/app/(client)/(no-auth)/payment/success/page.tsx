"use client";

import { motion } from "framer-motion";
import { CheckCircle2 } from "lucide-react";
import Link from "next/link";

export default function PaymentSuccess() {
    return (
        <div className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-b from-[#f7f4ff] to-[#ece8ff] px-6">
            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6 }}
                className="text-center"
            >
                <CheckCircle2 className="w-20 h-20 text-green-600 mx-auto mb-6" />

                <h1 className="text-3xl font-bold text-gray-900 mb-3">
                    Thanh toán thành công!
                </h1>
                <p className="text-gray-600 text-lg max-w-md mx-auto">
                    Cảm ơn bạn đã nâng cấp Premium. Tài khoản của bạn sẽ được
                    kích hoạt ngay lập tức.
                </p>

                <Link
                    href="/home"
                    className="mt-8 inline-block bg-purple-600 hover:bg-purple-700 text-white text-lg font-semibold px-8 py-3 rounded-xl shadow-lg transition"
                >
                    Quay lại trang chủ
                </Link>
            </motion.div>
        </div>
    );
}
