"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Fragment, useCallback, useEffect, useState } from "react";
import { Eye, Loader2, MessageCircle, Minus, ThumbsUp, TrendingDown, TrendingUp, Users } from "lucide-react";
import { api } from "@/utils/axiosInstance";
import { useAuth } from "@/auth/AuthProvider";
import UserAvatar from "@/share/components/UserAvatar";
import type { CommunityPost } from "@/store/community/community.reducer";
import { formatRelativeTime } from "@/app/(client)/(no-auth)/cong-dong/components/formatRelativeTime";

// Nhận định của bài đăng hiển thị như nhãn tích cực/tiêu cực cạnh mã cổ phiếu (kiểu FireAnt).
const SENTIMENT: Record<string, { text: string; Icon: typeof TrendingUp; className: string }> = {
    BUY: { text: "Tích cực", Icon: TrendingUp, className: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" },
    SELL: { text: "Tiêu cực", Icon: TrendingDown, className: "bg-rose-500/10 text-rose-600 dark:text-rose-400" },
    HOLD: { text: "Trung lập", Icon: Minus, className: "bg-amber-500/10 text-amber-600 dark:text-amber-400" },
};

const TABS = [
    { key: "all", label: "Mới nhất" },
    { key: "hot", label: "Nổi bật" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

/** Tô xanh các mã được gắn dạng $MÃ trong nội dung. */
function renderWithTickers(text: string) {
    return text.split(/(\$[A-Z0-9]{3,5})\b/g).map((part, i) =>
        /^\$[A-Z0-9]{3,5}$/.test(part) ? (
            <span key={i} className="font-semibold text-blue-600 dark:text-blue-400">
                {part}
            </span>
        ) : (
            <Fragment key={i}>{part}</Fragment>
        ),
    );
}

/** Luồng bài đăng Cộng đồng ở trang chủ, bố cục giống luồng thảo luận của FireAnt. */
export default function CommunityPostsWidget({ limit = 5 }: { limit?: number }) {
    const router = useRouter();
    const { user } = useAuth();
    const [tab, setTab] = useState<TabKey>("all");
    const [posts, setPosts] = useState<CommunityPost[] | null>(null);
    const [page, setPage] = useState(1);
    const [total, setTotal] = useState(0);
    const [loadingMore, setLoadingMore] = useState(false);

    const load = useCallback(
        async (nextPage: number) => {
            const res = await api.get("/community/posts", {
                params: { page: nextPage, limit, category: tab },
            });
            const data = res.data?.data;
            return { posts: (data?.posts ?? []) as CommunityPost[], total: Number(data?.total ?? 0) };
        },
        [limit, tab],
    );

    useEffect(() => {
        let cancelled = false;
        setPosts(null);
        load(1)
            .then((r) => {
                if (cancelled) return;
                setPosts(r.posts);
                setTotal(r.total);
                setPage(1);
            })
            .catch(() => {
                if (!cancelled) setPosts([]);
            });
        return () => {
            cancelled = true;
        };
    }, [load]);

    const loadMore = async () => {
        setLoadingMore(true);
        try {
            const r = await load(page + 1);
            setPosts((prev) => {
                const seen = new Set((prev ?? []).map((p) => p.id));
                return [...(prev ?? []), ...r.posts.filter((p) => !seen.has(p.id))];
            });
            setTotal(r.total);
            setPage(page + 1);
        } catch {
            // Giữ nguyên danh sách, người dùng bấm lại được.
        } finally {
            setLoadingMore(false);
        }
    };

    const toggleLike = async (post: CommunityPost) => {
        if (!user) {
            router.push("/login");
            return;
        }
        const liked = !post.isLiked;
        const patch = (p: Partial<CommunityPost>) =>
            setPosts((prev) => prev?.map((x) => (x.id === post.id ? { ...x, ...p } : x)) ?? prev);

        patch({ isLiked: liked, likes: post.likes + (liked ? 1 : -1) });
        try {
            const res = await api.post(`/community/posts/${post.id}/like`);
            const data = res.data?.data;
            if (data) patch({ isLiked: data.isLiked, likes: data.likesCount });
        } catch {
            patch({ isLiked: post.isLiked, likes: post.likes });
        }
    };

    const hasMore = posts !== null && posts.length < total;

    return (
        <section className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm overflow-hidden">
            <div className="px-4 pt-3 flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <Users className="w-4 h-4 text-indigo-500" />
                    <h2 className="font-bold text-sm text-slate-900 dark:text-white">Cộng đồng</h2>
                </div>
                <Link href="/cong-dong" className="text-xs font-semibold text-indigo-600 dark:text-indigo-400 hover:underline">
                    Xem tất cả
                </Link>
            </div>

            <div className="px-4 mt-2 flex gap-4 border-b border-slate-200/80 dark:border-slate-800">
                {TABS.map((t) => (
                    <button
                        key={t.key}
                        type="button"
                        onClick={() => setTab(t.key)}
                        className={`pb-2 -mb-px text-xs font-semibold border-b-2 transition-colors cursor-pointer ${
                            tab === t.key
                                ? "border-indigo-500 text-indigo-600 dark:text-indigo-400"
                                : "border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
                        }`}
                    >
                        {t.label}
                    </button>
                ))}
            </div>

            {posts === null ? (
                <div className="p-3 space-y-3">
                    {Array.from({ length: 3 }).map((_, i) => (
                        <div key={i} className="h-24 rounded-xl bg-slate-100 dark:bg-slate-800 animate-pulse" />
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
                        const sentiment = post.stance ? SENTIMENT[post.stance] : undefined;
                        const href = `/cong-dong#${post.id}`;
                        return (
                            <article key={post.id} className="px-4 py-3">
                                <div className="flex items-start gap-2.5">
                                    <UserAvatar src={post.authorAvatar} name={post.authorName} size={36} className="shrink-0" />
                                    <div className="min-w-0 flex-1">
                                        <div className="flex items-center gap-1.5 min-w-0">
                                            <span className="text-sm font-semibold text-slate-900 dark:text-slate-100 truncate">
                                                {post.authorName}
                                            </span>
                                            {post.authorBadge && post.authorBadge !== "Thành viên" && (
                                                <span className="shrink-0 text-[10px] font-bold px-1.5 py-px rounded bg-indigo-500/10 text-indigo-600 dark:text-indigo-400">
                                                    {post.authorBadge}
                                                </span>
                                            )}
                                        </div>
                                        <p className="text-[11px] text-slate-400">{formatRelativeTime(post.createdAt)}</p>
                                    </div>
                                </div>

                                <Link href={href} className="block mt-2 group">
                                    {post.title && (
                                        <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 line-clamp-2 wrap-anywhere group-hover:text-blue-600 dark:group-hover:text-blue-400">
                                            {post.title}
                                        </h3>
                                    )}
                                    <p className="text-sm leading-relaxed text-slate-700 dark:text-slate-300 line-clamp-3 wrap-anywhere">
                                        {renderWithTickers(post.content)}
                                    </p>
                                    {post.imageUrl && (
                                        // eslint-disable-next-line @next/next/no-img-element
                                        <img
                                            src={post.imageUrl}
                                            alt=""
                                            loading="lazy"
                                            onError={(e) => (e.currentTarget.style.display = "none")}
                                            className="mt-2 w-full max-h-40 object-cover rounded-lg border border-slate-200/60 dark:border-slate-700/60"
                                        />
                                    )}
                                </Link>

                                {post.symbol && (
                                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                                        <Link
                                            href={`/ma-chung-khoan/${post.symbol}`}
                                            className="text-xs font-bold px-2 py-0.5 rounded-md bg-blue-500/10 text-blue-600 dark:text-blue-400 hover:bg-blue-500/20"
                                        >
                                            {post.symbol}
                                        </Link>
                                        {sentiment && (
                                            <span className={`inline-flex items-center gap-1 text-[11px] font-semibold px-1.5 py-0.5 rounded-md ${sentiment.className}`}>
                                                <sentiment.Icon className="w-3 h-3" /> {sentiment.text}
                                            </span>
                                        )}
                                    </div>
                                )}

                                <div className="mt-2 flex items-center gap-4 text-xs text-slate-500 dark:text-slate-400">
                                    <button
                                        type="button"
                                        onClick={() => toggleLike(post)}
                                        className={`inline-flex items-center gap-1 cursor-pointer hover:text-blue-600 dark:hover:text-blue-400 ${
                                            post.isLiked ? "text-blue-600 dark:text-blue-400 font-semibold" : ""
                                        }`}
                                    >
                                        <ThumbsUp className="w-3.5 h-3.5" fill={post.isLiked ? "currentColor" : "none"} />
                                        {post.likes}
                                    </button>
                                    <Link href={href} className="inline-flex items-center gap-1 hover:text-blue-600 dark:hover:text-blue-400">
                                        <MessageCircle className="w-3.5 h-3.5" /> {post.commentsCount}
                                    </Link>
                                    <span className="inline-flex items-center gap-1">
                                        <Eye className="w-3.5 h-3.5" /> {post.viewsCount ?? 0}
                                    </span>
                                </div>
                            </article>
                        );
                    })}
                </div>
            )}

            {hasMore && (
                <button
                    type="button"
                    onClick={loadMore}
                    disabled={loadingMore}
                    className="w-full py-2.5 border-t border-slate-200/80 dark:border-slate-800 text-xs font-semibold text-indigo-600 dark:text-indigo-400 hover:bg-slate-50 dark:hover:bg-slate-800/60 inline-flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-60"
                >
                    {loadingMore && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                    Xem thêm bài đăng
                </button>
            )}
        </section>
    );
}
