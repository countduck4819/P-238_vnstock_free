"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Heart, MessageSquare, Users } from "lucide-react";
import { api } from "@/utils/axiosInstance";
import UserAvatar from "@/share/components/UserAvatar";
import type { CommunityPost } from "@/store/community/community.reducer";
import { formatRelativeTime } from "@/app/(client)/(no-auth)/cong-dong/components/formatRelativeTime";

const STANCE_LABEL: Record<string, { text: string; className: string }> = {
    BUY: { text: "MUA", className: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" },
    SELL: { text: "BÁN", className: "bg-rose-500/10 text-rose-600 dark:text-rose-400" },
    HOLD: { text: "THEO DÕI", className: "bg-amber-500/10 text-amber-600 dark:text-amber-400" },
};

/** Vài bài đăng mới nhất của Cộng đồng, bấm vào mở đúng bài trên trang Cộng đồng. */
export default function CommunityPostsWidget({ limit = 5 }: { limit?: number }) {
    const [posts, setPosts] = useState<CommunityPost[] | null>(null);

    useEffect(() => {
        let cancelled = false;
        api.get("/community/posts", { params: { page: 1, limit } })
            .then((res) => {
                if (!cancelled) setPosts(res.data?.data?.posts ?? []);
            })
            .catch(() => {
                if (!cancelled) setPosts([]);
            });
        return () => {
            cancelled = true;
        };
    }, [limit]);

    return (
        <section className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-200/80 dark:border-slate-800 flex items-center justify-between bg-slate-50/70 dark:bg-slate-900/90">
                <div className="flex items-center gap-2">
                    <Users className="w-4 h-4 text-indigo-500" />
                    <h2 className="font-bold text-sm text-slate-900 dark:text-white">Bài đăng cộng đồng</h2>
                </div>
                <Link href="/cong-dong" className="text-xs font-semibold text-indigo-600 dark:text-indigo-400 hover:underline">
                    Xem tất cả
                </Link>
            </div>

            {posts === null ? (
                <div className="p-3 space-y-3">
                    {Array.from({ length: 3 }).map((_, i) => (
                        <div key={i} className="h-16 rounded-xl bg-slate-100 dark:bg-slate-800 animate-pulse" />
                    ))}
                </div>
            ) : posts.length === 0 ? (
                <p className="p-5 text-center text-sm text-slate-500 dark:text-slate-400">
                    Chưa có bài đăng nào.{" "}
                    <Link href="/cong-dong" className="text-indigo-600 dark:text-indigo-400 font-semibold">
                        Đăng bài đầu tiên
                    </Link>
                </p>
            ) : (
                <div className="divide-y divide-slate-100 dark:divide-slate-800/80">
                    {posts.map((post) => {
                        const stance = post.stance ? STANCE_LABEL[post.stance] : undefined;
                        return (
                            <Link
                                key={post.id}
                                href={`/cong-dong#${post.id}`}
                                className="block p-3 hover:bg-slate-50 dark:hover:bg-slate-800/60 transition-colors"
                            >
                                <div className="flex items-center gap-2 mb-1.5 min-w-0">
                                    <UserAvatar src={post.authorAvatar} name={post.authorName} size={24} className="shrink-0" />
                                    <span className="text-xs font-semibold text-slate-800 dark:text-slate-200 truncate">
                                        {post.authorName}
                                    </span>
                                    <span className="text-[11px] text-slate-400 whitespace-nowrap">
                                        {formatRelativeTime(post.createdAt)}
                                    </span>
                                    {post.symbol && (
                                        <span className="ml-auto text-[11px] font-bold text-blue-600 dark:text-blue-400 shrink-0">
                                            ${post.symbol}
                                        </span>
                                    )}
                                    {stance && (
                                        <span className={`text-[10px] font-extrabold px-1.5 py-0.5 rounded shrink-0 ${post.symbol ? "" : "ml-auto"} ${stance.className}`}>
                                            {stance.text}
                                        </span>
                                    )}
                                </div>
                                <p className="text-sm text-slate-700 dark:text-slate-300 line-clamp-2 wrap-anywhere">
                                    {post.title ? <b className="font-semibold text-slate-900 dark:text-slate-100">{post.title}. </b> : null}
                                    {post.content}
                                </p>
                                <div className="flex items-center gap-3 mt-1.5 text-[11px] text-slate-400">
                                    <span className="inline-flex items-center gap-1">
                                        <Heart className="w-3 h-3" /> {post.likes}
                                    </span>
                                    <span className="inline-flex items-center gap-1">
                                        <MessageSquare className="w-3 h-3" /> {post.commentsCount}
                                    </span>
                                </div>
                            </Link>
                        );
                    })}
                </div>
            )}
        </section>
    );
}
