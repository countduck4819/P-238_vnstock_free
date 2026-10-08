"use client";

import Image from "next/image";
import { useEffect } from "react";
import { useDispatch } from "react-redux";
import { AppDispatch, RootState } from "@/redux/store";
import { useAppSelector } from "@/redux/hooks";
import { fetchAllNewsForVNINDEX } from "@/store/news/news.api";
import { useRouter } from "next/navigation";

function formatTimeAgo(dateStr?: string) {
    if (!dateStr) return "";
    const date = new Date(dateStr);
    const diff = Math.floor((Date.now() - date.getTime()) / 60000);
    if (diff < 1) return "vừa xong";
    if (diff < 60) return `${diff} phút`;
    const hours = Math.floor(diff / 60);
    if (hours < 24) return `Khoảng ${hours} tiếng`;
    return `${date?.getDate()}/${date?.getMonth() + 1}`;
}

export default function RightPanel() {
    const router = useRouter();
    const dispatch = useDispatch<AppDispatch>();
    const { vnindexList, loading } = useAppSelector((s: RootState) => s.news);

    /** 🔹 Lấy danh sách tin mới nhất */
    useEffect(() => {
        dispatch(fetchAllNewsForVNINDEX({ page: 1, limit: 35 }));
    }, [dispatch]);

    return (
        <div className="relative z-[0] w-full h-auto lg:h-full bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 shadow-xs overflow-hidden flex flex-col transition-colors">
            {/* Header (Sticky ở đầu khung trên Desktop) */}
            <div className="sticky top-0 z-10 px-4 py-3 bg-white/95 dark:bg-slate-900/95 backdrop-blur-md border-b border-slate-100 dark:border-slate-800/80 flex justify-between items-center shrink-0">
                <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-indigo-500 animate-pulse" />
                    <h2 className="text-sm font-bold text-slate-800 dark:text-white">
                        Bài viết nổi bật
                    </h2>
                </div>
                {vnindexList?.length > 0 && (
                    <span className="text-[11px] font-medium text-slate-400">
                        {vnindexList.length} bài
                    </span>
                )}
            </div>

            {/* Danh sách bài viết: Trên Mobile bung dài tự nhiên kéo xuống được, Trên Desktop cuộn độc lập */}
            <div className="flex-1 lg:min-h-0 lg:overflow-y-auto divide-y divide-slate-100 dark:divide-slate-800/60">
                {loading && (
                    <div className="text-xs text-slate-400 p-4 text-center">
                        Đang tải tin tức...
                    </div>
                )}

                {!vnindexList?.length ? (
                    <div className="text-slate-500 dark:text-slate-400 p-6 text-center text-xs">
                        Hiện chưa có tin tức nào
                    </div>
                ) : (
                    vnindexList.map((item) => (
                        <div
                            key={item.news_id}
                            onClick={() => router.push(`/tin-tuc/${item.slug}`)}
                            className="flex gap-3 p-3 cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/60 transition-colors group"
                        >
                            <div className="relative w-16 h-12 rounded-lg overflow-hidden flex-shrink-0 bg-slate-100 dark:bg-slate-800">
                                {item.news_image_url ? (
                                    <Image
                                        src={item.news_image_url}
                                        alt={item.news_title}
                                        fill
                                        sizes="64px"
                                        className="object-cover group-hover:scale-105 transition-transform duration-200"
                                    />
                                ) : (
                                    <div className="text-[10px] flex items-center justify-center h-full text-slate-400">
                                        FinSight
                                    </div>
                                )}
                            </div>

                            <div className="flex-1 min-w-0 flex flex-col justify-between">
                                <p className="text-xs text-slate-800 dark:text-slate-200 leading-snug font-medium line-clamp-2 group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors">
                                    {item.news_title}
                                </p>
                                <span className="block text-[11px] text-slate-400 mt-1">
                                    {formatTimeAgo(item.public_date)}
                                </span>
                            </div>
                        </div>
                    ))
                )}
            </div>
        </div>
    );
}
