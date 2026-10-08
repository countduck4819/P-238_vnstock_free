"use client";

import { useEffect } from "react";
import { motion } from "framer-motion";
import CountUp from "react-countup";
import { useAppDispatch, useAppSelector } from "@/redux/hooks";
import { fetchStocks } from "@/store/stock-symbols/stock-symbols.api";
import { fetchAllNewsForVNINDEX } from "@/store/news/news.api";

// Redux

export default function AdminWelcomePage() {
    const dispatch = useAppDispatch();

    // Lấy số liệu từ store
    const stocks = useAppSelector((state) => state.stockSymbols.stocksFullList);
    const newsTotal = useAppSelector(
        (state) => state.news.vnindexMeta?.total || 1205
    );

    // Giả sử user chưa có API → tạm để 0
    const totalUsers = 4819;

    useEffect(() => {
        dispatch(fetchStocks());
        dispatch(fetchAllNewsForVNINDEX({ page: 1, limit: 10 }));
    }, []);

    return (
        <div className="w-full h-full px-8 py-10 text-white">
            <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5 }}
                className="mb-10"
            >
                <h1 className="text-4xl pb-[0.5rem] font-bold mb-2 bg-gradient-to-r from-purple-300 to-pink-400 bg-clip-text text-transparent">
                    Chào mừng đến với hệ thống quản trị FinSight
                </h1>
                <p className="text-gray-300 text-lg">
                    Đây là trung tâm điều khiển giúp bạn quản lý người dùng, dữ
                    liệu cổ phiếu, tin tức, dự báo AI và toàn bộ hệ thống.
                </p>
            </motion.div>

            {/* THẺ TỔNG QUAN */}
            <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.2 }}
                className="grid grid-cols-1 md:grid-cols-3 gap-6"
            >
                {/* USERS */}
                <div className="bg-gradient-to-b from-purple-700/30 to-purple-900/20 border border-purple-600/30 rounded-xl p-6 shadow-lg hover:shadow-purple-500/20 transition">
                    <h3 className="text-xl font-semibold mb-1">Người dùng</h3>

                    <p className="text-3xl font-bold text-purple-300">
                        <CountUp end={totalUsers} duration={6} separator="," />
                    </p>

                    <p className="text-gray-400 mt-1 text-sm">
                        Tổng số tài khoản
                    </p>
                </div>

                {/* STOCKS */}
                <div className="bg-gradient-to-b from-purple-700/30 to-purple-900/20 border border-purple-600/30 rounded-xl p-6 shadow-lg hover:shadow-purple-500/20 transition">
                    <h3 className="text-xl font-semibold mb-1">Cổ phiếu</h3>

                    <p className="text-3xl font-bold text-purple-300">
                        <CountUp
                            end={stocks.length}
                            duration={5}
                            separator=","
                        />
                    </p>

                    <p className="text-gray-400 mt-1 text-sm">
                        Tổng số các mã cổ phiếu
                    </p>
                </div>

                {/* NEWS */}
                <div className="bg-gradient-to-b from-purple-700/30 to-purple-900/20 border border-purple-600/30 rounded-xl p-6 shadow-lg hover:shadow-purple-500/20 transition">
                    <h3 className="text-xl font-semibold mb-1">Tin tức</h3>

                    <p className="text-3xl font-bold text-purple-300">
                        <CountUp end={newsTotal} duration={5} separator="," />
                    </p>

                    <p className="text-gray-400 mt-1 text-sm">Tin thị trường</p>
                </div>
            </motion.div>

            {/* GIỚI THIỆU */}
            <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.4 }}
                className="mt-12 bg-white/5 border border-white/10 rounded-xl p-8 backdrop-blur-xl"
            >
                <h2 className="text-2xl font-semibold mb-4">
                    Giới thiệu nhanh
                </h2>

                <p className="text-gray-300 leading-relaxed">
                    Hệ thống quản trị FinSight là nền tảng dành cho quản trị viên
                    nhằm quản lý, kiểm soát hoạt động của toàn bộ hệ thống:
                    user, nhóm ngành, dữ liệu cổ phiếu, tin tức, xu hướng thị
                    trường, dự báo AI & khuyến nghị AI.
                </p>

                <p className="text-gray-300 mt-3 leading-relaxed">
                    Hãy sử dụng menu bên trái để bắt đầu thao tác. Chúc bạn có
                    trải nghiệm tốt khi vận hành hệ thống!
                </p>
            </motion.div>
        </div>
    );
}
