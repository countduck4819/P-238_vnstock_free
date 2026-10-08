"use client";

import { motion } from "framer-motion";
import { XCircle } from "lucide-react";
import Link from "next/link";

export default function PaymentCancel() {
    return (
        <div className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-b from-[#fff5f5] to-[#ffeaea] px-6">
            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6 }}
                className="text-center"
            >
                <XCircle className="w-20 h-20 text-red-600 mx-auto mb-6" />

                <h1 className="text-3xl font-bold text-gray-900 mb-3">
                    Thanh toán bị hủy
                </h1>
                <p className="text-gray-600 text-lg max-w-md mx-auto">
                    Giao dịch chưa hoàn tất. Bạn có thể thử lại bất cứ lúc nào.
                </p>

                <Link
                    href="/nang-cap-hoi-vien"
                    className="mt-8 inline-block bg-purple-600 hover:bg-purple-700 text-white text-lg font-semibold px-8 py-3 rounded-xl shadow-lg transition"
                >
                    Quay lại trang Premium
                </Link>
            </motion.div>
        </div>
    );
}
