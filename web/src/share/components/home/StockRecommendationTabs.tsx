"use client";
import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";

import ExpertRecommendations from "./ExpertRecommendations";
import H120TrendAdvisory from "./H120TrendAdvisory";
import V6LongTermAdvisory from "./V6LongTermAdvisory";

import { useAuth } from "@/auth/AuthProvider";
import { canAccess } from "@/lib/utils";
import UpgradeToPremium from "../updatePremium/UpgradeToPremium";
import { AccountType } from "@/store/users/user.reducer";
import { Role } from "@/share/enum";
import { Telescope, TrendingUp, UserCheck } from "lucide-react";

export default function StockRecommendationTabs() {
    const { user } = useAuth();

    const [activeTab, setActiveTab] = useState("expert");
    const handleTabChange = (val: string) => {
        setActiveTab(val);
    };

    useEffect(() => {
        const checkHashOrQuery = () => {
            const params = new URLSearchParams(window.location.search);
            const tabParam = params.get("tab");
            const hash = window.location.hash.replace("#", "");

            if (tabParam === "h120" || hash === "h120") {
                setActiveTab("h120");
            } else if (
                tabParam === "long-term" ||
                hash === "long-term" ||
                tabParam === "ai" ||
                hash === "ai"
            ) {
                setActiveTab("long-term");
            } else if (tabParam === "expert" || hash === "expert") {
                setActiveTab("expert");
            }
        };

        checkHashOrQuery();

        const handleCustomTabSwitch = (e: Event) => {
            const customEvent = e as CustomEvent<string>;
            if (customEvent.detail) {
                setActiveTab(customEvent.detail === "ai" ? "long-term" : customEvent.detail);
            }
        };

        window.addEventListener("switch-stock-tab", handleCustomTabSwitch);
        window.addEventListener("hashchange", checkHashOrQuery);

        return () => {
            window.removeEventListener("switch-stock-tab", handleCustomTabSwitch);
            window.removeEventListener("hashchange", checkHashOrQuery);
        };
    }, []);

    const canSeeContent = canAccess(user, Role.User, AccountType.PREMIUM);
const shortTermEnabled =
    process.env.NEXT_PUBLIC_SHORT_TERM_ENABLED !== "false" &&
    process.env.NEXT_PUBLIC_H120_ENABLED !== "false";

const longTermEnabled =
    process.env.NEXT_PUBLIC_LONG_TERM_ENABLED !== "false" ||
    process.env.NEXT_PUBLIC_V6_ENABLED !== "false";
    return (
        <div id="stock-recommendations-section" className="w-full mt-6 space-y-4 scroll-mt-20">
            <Tabs
                value={activeTab}
                onValueChange={handleTabChange}
                className="w-full"
            >
                {/* --- TAB HEADER --- */}
                <div className="flex flex-col gap-3 border-b border-slate-200/80 pb-3 dark:border-slate-800 xl:flex-row xl:items-center xl:justify-between">
                    <div className="w-full rounded-2xl border border-slate-200/80 bg-slate-100/90 p-1.5 shadow-xs backdrop-blur-md dark:border-slate-800 dark:bg-slate-900/90 sm:w-fit">
                        <TabsList className="grid grid-cols-3 sm:flex items-center gap-1 sm:gap-1.5 bg-transparent p-0 w-full h-auto">
                            <TabsTrigger
                                value="expert"
                                className={`
                                    flex items-center justify-center gap-1 sm:gap-2 px-1.5 sm:px-4 py-2 text-xs sm:text-sm font-medium rounded-xl transition-all duration-200 select-none cursor-pointer
                                    ${
                                        activeTab === "expert"
                                            ? "bg-white dark:bg-slate-800 text-indigo-600 dark:text-white font-semibold shadow-xs"
                                            : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200"
                                    }`}
                            >
                                <UserCheck className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-indigo-600 dark:text-indigo-400 shrink-0" />
                                <span className="sm:hidden truncate">Chuyên gia</span>
                                <span className="hidden sm:inline">Từ chuyên gia</span>
                            </TabsTrigger>

                            {shortTermEnabled && (
                                <TabsTrigger
                                    value="short-term"
                                    className={`
                                        flex items-center justify-center gap-1 sm:gap-2 px-1.5 sm:px-4 py-2 text-xs sm:text-sm font-medium rounded-xl transition-all duration-200 select-none cursor-pointer
                                        ${
                                            activeTab === "short-term"
                                                ? "bg-white dark:bg-slate-800 text-emerald-600 dark:text-white font-semibold shadow-xs"
                                                : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200"
                                        }`}
                                >
                                    <TrendingUp className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
                                    <span className="sm:hidden truncate">Ngắn hạn</span>
                                    <span className="hidden sm:inline">Xu hướng ngắn hạn</span>
                                </TabsTrigger>
                            )}
                            {longTermEnabled && (
                                <TabsTrigger
                                    value="long-term"
                                    className={`
                                        flex items-center justify-center gap-1 sm:gap-2 px-1.5 sm:px-4 py-2 text-xs sm:text-sm font-medium rounded-xl transition-all duration-200 select-none cursor-pointer
                                        ${
                                            activeTab === "long-term"
                                                ? "bg-white dark:bg-slate-800 text-blue-600 dark:text-white font-semibold shadow-xs"
                                                : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200"
                                        }`}
                                >
                                    <Telescope className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-blue-600 dark:text-blue-400 shrink-0" />
                                    <span className="sm:hidden truncate">Dài hạn + AI</span>
                                    <span className="hidden sm:inline">Xu hướng dài hạn + Dự đoán giá</span>
                                </TabsTrigger>
                            )}
                        </TabsList>
                    </div>

                    <div className="hidden shrink-0 items-center gap-2 text-xs text-slate-500 dark:text-slate-400 sm:flex">
                        <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                        <span>Tín hiệu realtime</span>
                    </div>
                </div>

                {/* --- TAB CONTENT --- */}
                <div className="mt-4">
                    {/* EXPERT */}
                    <TabsContent value="expert" className="mt-0">
                        <AnimatePresence mode="wait">
                            {canSeeContent ? (
                                <motion.div
                                    key="expert"
                                    initial={{ opacity: 0, y: 6 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    exit={{ opacity: 0, y: -6 }}
                                    transition={{ duration: 0.22 }}
                                >
                                    <ExpertRecommendations />
                                </motion.div>
                            ) : (
                                <motion.div
                                    key="premium-expert"
                                    initial={{ opacity: 0, y: 6 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    exit={{ opacity: 0, y: -6 }}
                                    transition={{ duration: 0.22 }}
                                >
                                    <UpgradeToPremium activeTab={activeTab} />
                                </motion.div>
                            )}
                        </AnimatePresence>
                    </TabsContent>

                    {shortTermEnabled && (
                        <TabsContent value="short-term" className="mt-0">
                            <AnimatePresence mode="wait">
                                {canSeeContent ? (
                                    <motion.div
                                        key="short-term"
                                        initial={{ opacity: 0, y: 6 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        exit={{ opacity: 0, y: -6 }}
                                        transition={{ duration: 0.22 }}
                                    >
                                        <div className="bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 rounded-2xl p-5 md:p-6 shadow-sm">
                                            <H120TrendAdvisory />
                                        </div>
                                    </motion.div>
                                ) : (
                                    <motion.div
                                        key="premium-short-term"
                                        initial={{ opacity: 0, y: 6 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        exit={{ opacity: 0, y: -6 }}
                                        transition={{ duration: 0.22 }}
                                    >
                                        <UpgradeToPremium activeTab={activeTab} />
                                    </motion.div>
                                )}
                            </AnimatePresence>
                        </TabsContent>
                    )}
                    {longTermEnabled && (
                        <TabsContent value="long-term" className="mt-0">
                            <AnimatePresence mode="wait">
                                {canSeeContent ? (
                                    <motion.div
                                        key="long-term"
                                        initial={{ opacity: 0, y: 6 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        exit={{ opacity: 0, y: -6 }}
                                        transition={{ duration: 0.22 }}
                                    >
                                        <div className="bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 rounded-2xl p-5 md:p-6 shadow-sm">
                                            <V6LongTermAdvisory />
                                        </div>
                                    </motion.div>
                                ) : (
                                    <motion.div
                                        key="premium-long-term"
                                        initial={{ opacity: 0, y: 6 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        exit={{ opacity: 0, y: -6 }}
                                        transition={{ duration: 0.22 }}
                                    >
                                        <UpgradeToPremium activeTab={activeTab} />
                                    </motion.div>
                                )}
                            </AnimatePresence>
                        </TabsContent>
                    )}
                </div>
            </Tabs>
        </div>
    );
}
