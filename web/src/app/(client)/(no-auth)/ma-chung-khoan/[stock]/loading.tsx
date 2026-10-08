"use client";

import { Activity, BarChart3, Clock, Layers, Sparkles } from "lucide-react";

export default function StockDetailLoading() {
    return (
        <div className="max-w-[90vw] mx-auto flex flex-col gap-6 py-6 animate-pulse">
            {/* Top Header Card Skeleton */}
            <div className="bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 rounded-2xl p-6 shadow-sm">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                    {/* Left Skeleton */}
                    <div className="space-y-2.5">
                        <div className="flex items-center gap-3">
                            <div className="w-16 h-8 rounded-lg bg-indigo-500/20 dark:bg-indigo-500/30 animate-pulse" />
                            <div className="w-48 sm:w-64 h-6 rounded-lg bg-slate-200 dark:bg-slate-800" />
                        </div>
                        <div className="flex items-center gap-2">
                            <div className="w-20 h-4 rounded bg-slate-200 dark:bg-slate-800" />
                            <span className="text-slate-300 dark:text-slate-700">•</span>
                            <div className="w-32 h-4 rounded bg-slate-200 dark:bg-slate-800" />
                        </div>
                    </div>

                    {/* Right Price Skeleton */}
                    <div className="space-y-2 text-left sm:text-right">
                        <div className="w-28 sm:w-36 h-9 rounded-xl bg-slate-200 dark:bg-slate-800 ml-auto" />
                        <div className="w-20 sm:w-24 h-4 rounded-lg bg-slate-200 dark:bg-slate-800 ml-auto" />
                    </div>
                </div>
            </div>

            {/* Main Grid: Chart + Overview */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Left: Chart + News Skeleton */}
                <div className="lg:col-span-2 space-y-6">
                    {/* Chart Container Skeleton */}
                    <div className="w-full h-[540px] rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm overflow-hidden flex flex-col">
                        {/* Toolbar Skeleton */}
                        <div className="px-4 py-3 border-b border-slate-200/80 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-900/90 flex items-center justify-between">
                            <div className="flex items-center gap-3">
                                <div className="w-14 h-7 rounded-lg bg-indigo-500/20" />
                                <div className="w-32 h-7 rounded-lg bg-slate-200 dark:bg-slate-800" />
                            </div>
                            <div className="flex items-center gap-2">
                                <div className="w-24 h-7 rounded-lg bg-slate-200 dark:bg-slate-800" />
                                <div className="w-36 h-7 rounded-lg bg-slate-200 dark:bg-slate-800" />
                            </div>
                        </div>

                        {/* OHLC Bar Skeleton */}
                        <div className="px-4 py-2 bg-slate-900/95 dark:bg-slate-950/95 border-b border-slate-800 flex items-center gap-4">
                            <div className="w-24 h-4 rounded bg-slate-800" />
                            <div className="w-40 h-4 rounded bg-slate-800" />
                            <div className="w-32 h-4 rounded bg-slate-800 ml-auto" />
                        </div>

                        {/* Chart Area Animation */}
                        <div className="flex-1 flex flex-col items-center justify-center relative overflow-hidden bg-slate-950/40">
                            <div className="absolute inset-0 bg-gradient-to-r from-transparent via-indigo-500/5 to-transparent animate-shimmer" />
                            <div className="flex flex-col items-center gap-3 z-10">
                                <div className="relative">
                                    <div className="w-12 h-12 rounded-2xl bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center text-indigo-400">
                                        <BarChart3 className="w-6 h-6 animate-pulse" />
                                    </div>
                                    <span className="absolute -top-1 -right-1 w-3 h-3 bg-indigo-500 rounded-full animate-ping" />
                                </div>
                                <span className="text-sm font-semibold text-slate-300">
                                    Đang nạp dữ liệu nến & chỉ báo kỹ thuật...
                                </span>
                                <span className="text-xs text-slate-500 font-mono">
                                    Tối ưu hóa hiển thị thời gian thực
                                </span>
                            </div>
                        </div>
                    </div>

                    {/* News Skeleton Cards */}
                    <div className="space-y-3">
                        <div className="w-32 h-6 rounded-lg bg-slate-200 dark:bg-slate-800" />
                        {[1, 2, 3].map((i) => (
                            <div
                                key={i}
                                className="min-h-[9rem] flex items-start gap-4 rounded-xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900/60 p-4"
                            >
                                <div className="w-[7.5rem] aspect-[4/3] rounded-lg bg-slate-200 dark:bg-slate-800 shrink-0" />
                                <div className="flex-1 space-y-2.5">
                                    <div className="w-24 h-4 rounded bg-slate-200 dark:bg-slate-800" />
                                    <div className="w-full h-5 rounded bg-slate-200 dark:bg-slate-800" />
                                    <div className="w-3/4 h-4 rounded bg-slate-200 dark:bg-slate-800" />
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Right: Overview Skeleton */}
                <div>
                    <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-sm overflow-hidden">
                        <div className="flex border-b border-slate-200 dark:border-slate-800 bg-[#F5F9FF] dark:bg-slate-800/70 items-center justify-between px-4 py-3">
                            <div className="w-24 h-5 rounded bg-slate-200 dark:bg-slate-700" />
                            <div className="w-12 h-4 rounded bg-slate-200 dark:bg-slate-700" />
                        </div>
                        <div className="divide-y divide-gray-100 dark:divide-slate-800/80 p-4 space-y-3">
                            {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((i) => (
                                <div key={i} className="flex justify-between py-1.5 items-center">
                                    <div className="w-24 h-4 rounded bg-slate-200 dark:bg-slate-800" />
                                    <div className="w-16 h-4 rounded bg-slate-200 dark:bg-slate-800" />
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
