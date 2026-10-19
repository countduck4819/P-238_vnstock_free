"use client";

import Image from "next/image";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, Newspaper, RefreshCw } from "lucide-react";
import { api } from "@/utils/axiosInstance";
import { formatRelativeTime } from "@/app/(client)/(no-auth)/cong-dong/components/formatRelativeTime";

interface NewsItem {
    id: number;
    news_id: string;
    news_title: string;
    news_short_content?: string | null;
    news_image_url?: string | null;
    public_date?: string | null;
    slug?: string | null;
    symbol?: string | null;
}

const PAGE_SIZE = 10;

function formatDate(value?: string | null) {
    if (!value) return "";
    const date = new Date(value);
    if (isNaN(date.getTime())) return "";
    return date.toLocaleString("vi-VN", {
        day: "2-digit",
        month: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
    });
}

/**
 * Bảng tin thị trường ở trang chủ: tin của mọi mã đã lưu trong DB (NestJS tự
 * lấy về theo lịch), mới nhất trước, cuộn tới đâu tải thêm 10 bài tới đó.
 */
export default function MarketNewsFeed() {
    const [items, setItems] = useState<NewsItem[]>([]);
    const [page, setPage] = useState(0);
    const [hasMore, setHasMore] = useState(true);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const loadingRef = useRef(false);
    const triggerRef = useRef<HTMLDivElement | null>(null);

    const loadPage = useCallback(async (nextPage: number) => {
        if (loadingRef.current) return;
        loadingRef.current = true;
        setLoading(true);
        setError(null);

        try {
            const res = await api.get("/news", {
                params: { page: nextPage, limit: PAGE_SIZE },
            });
            const data: NewsItem[] = res.data?.data ?? [];
            const meta = res.data?.meta;

            setItems((prev) => {
                const seen = new Set(prev.map((n) => n.news_id));
                return nextPage === 1
                    ? data
                    : [...prev, ...data.filter((n) => !seen.has(n.news_id))];
            });
            setPage(nextPage);
            setHasMore(Boolean(meta?.hasMore));
        } catch {
            setError("Không tải được tin tức");
        } finally {
            loadingRef.current = false;
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        loadPage(1);
    }, [loadPage]);

    useEffect(() => {
        const trigger = triggerRef.current;
        if (!trigger || !hasMore || error) return;

        const observer = new IntersectionObserver(
            (entries) => {
                if (entries[0]?.isIntersecting) loadPage(page + 1);
            },
            { rootMargin: "300px 0px" },
        );
        observer.observe(trigger);
        return () => observer.disconnect();
    }, [page, hasMore, error, loadPage]);

    return (
        <section className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm overflow-hidden">
            <div className="relative px-4 py-3.5 flex items-center gap-3 border-b border-slate-200/80 dark:border-slate-800">
                <span className="absolute left-0 top-3.5 bottom-3.5 w-1 rounded-r bg-blue-500" aria-hidden="true" />
                <span className="w-9 h-9 rounded-xl bg-blue-500/10 text-blue-600 dark:text-blue-400 flex items-center justify-center">
                    <Newspaper className="w-[18px] h-[18px]" />
                </span>
                <div>
                    <h2 className="font-bold text-[15px] leading-tight text-slate-900 dark:text-white">Bài viết &amp; tin tức</h2>
                    <p className="text-xs text-slate-500 dark:text-slate-400">Cập nhật liên tục các diễn biến mới nhất</p>
                </div>
            </div>

            <div className="divide-y divide-slate-100 dark:divide-slate-800/80">
                {items.map((item) => (
                    <Link
                        key={item.news_id}
                        href={`/tin-tuc/${item.slug}`}
                        className="group flex items-start gap-3 sm:gap-4 p-3 sm:p-4 hover:bg-slate-50 dark:hover:bg-slate-800/60 transition-colors"
                    >
                        <div className="relative w-24 sm:w-36 aspect-[4/3] shrink-0 rounded-lg overflow-hidden bg-slate-100 dark:bg-slate-800 border border-slate-200/60 dark:border-slate-700/60">
                            {item.news_image_url ? (
                                <Image
                                    src={item.news_image_url}
                                    alt={item.news_title}
                                    fill
                                    sizes="128px"
                                    className="object-cover transition-transform duration-300 group-hover:scale-105"
                                />
                            ) : (
                                <div className="flex items-center justify-center w-full h-full text-slate-400 dark:text-slate-500">
                                    <Newspaper className="w-6 h-6" />
                                </div>
                            )}
                        </div>

                        <div className="flex-1 min-w-0">
                            {item.symbol && (
                                <span className="inline-block mb-1.5 px-2 py-0.5 rounded-md border border-slate-200 dark:border-slate-700 text-[11px] font-bold text-slate-700 dark:text-slate-200">
                                    {item.symbol}
                                </span>
                            )}
                            <h3 className="text-sm sm:text-base font-semibold text-slate-900 dark:text-slate-100 line-clamp-2 group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">
                                {item.news_title}
                            </h3>
                            {item.news_short_content && (
                                <p className="hidden sm:block text-sm text-slate-600 dark:text-slate-300 line-clamp-2 mt-1">
                                    {item.news_short_content}
                                </p>
                            )}
                            {item.public_date && (
                                <p className="text-xs text-slate-400 mt-1.5" title={formatDate(item.public_date)}>
                                    {formatRelativeTime(item.public_date)}
                                </p>
                            )}
                        </div>
                    </Link>
                ))}
            </div>

            {!loading && !error && items.length === 0 && (
                <p className="p-6 text-center text-sm text-slate-500 dark:text-slate-400">
                    Chưa có tin tức. Hệ thống đang lấy tin từ vnstock, bạn quay lại sau ít phút nhé.
                </p>
            )}

            {error && (
                <div className="p-4 flex items-center justify-center gap-3 text-sm text-rose-500">
                    {error}
                    <button
                        type="button"
                        onClick={() => loadPage(page + 1)}
                        className="inline-flex items-center gap-1 text-indigo-600 dark:text-indigo-400 font-semibold cursor-pointer"
                    >
                        <RefreshCw className="w-3.5 h-3.5" /> Thử lại
                    </button>
                </div>
            )}

            {loading && (
                <div className="p-4 flex items-center justify-center gap-2 text-sm text-slate-500 dark:text-slate-400">
                    <Loader2 className="w-4 h-4 animate-spin" /> Đang tải tin tức...
                </div>
            )}

            <div ref={triggerRef} className="h-px" aria-hidden="true" />
        </section>
    );
}
