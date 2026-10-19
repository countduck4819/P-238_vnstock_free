"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Fragment, useCallback, useEffect, useState } from "react";
import { toast } from "react-toastify";
import { ArrowRight, Loader2, MessageSquare, MessagesSquare, MoreHorizontal, Share2, ThumbsUp } from "lucide-react";
import { api } from "@/utils/axiosInstance";
import { useAuth } from "@/auth/AuthProvider";
import UserAvatar from "@/share/components/UserAvatar";
import type { CommunityPost } from "@/store/community/community.reducer";
import { formatRelativeTime } from "@/app/(client)/(no-auth)/cong-dong/components/formatRelativeTime";

const MAX_CHIPS = 3;
const TOKEN_RE = /(https?:\/\/[^\s]+|\$[A-Z0-9]{3,8}\b)/g;

/** Nội dung chữ thường, đường link và $MÃ tô xanh như FireAnt. */
function renderContent(text: string) {
    return text.split(TOKEN_RE).map((part, i) => {
        if (/^https?:\/\//.test(part)) {
            return (
                <a
                    key={i}
                    href={part}
                    target="_blank"
                    rel="noopener noreferrer nofollow"
                    onClick={(e) => e.stopPropagation()}
                    className="text-blue-600 dark:text-blue-400 hover:underline"
                >
                    {part}
                </a>
            );
        }
        if (/^\$[A-Z0-9]{3,8}$/.test(part)) {
            return (
                <span key={i} className="text-blue-600 dark:text-blue-400">
                    {part}
                </span>
            );
        }
        return <Fragment key={i}>{part}</Fragment>;
    });
}

/** Mã được gắn của bài: mã chính trước, sau đó các $MÃ nhắc trong tiêu đề và nội dung. */
function postSymbols(post: CommunityPost) {
    const found = `${post.title ?? ""} ${post.content}`.match(/\$[A-Z0-9]{3,8}\b/g) ?? [];
    return [...new Set([post.symbol, ...found.map((s) => s.slice(1))].filter(Boolean) as string[])];
}

/** Cột "Thảo luận - Góc nhìn cộng đồng", bố cục theo khối thảo luận của FireAnt. */
export default function CommunityPostsWidget({ limit = 5 }: { limit?: number }) {
    const router = useRouter();
    const { user } = useAuth();
    const [posts, setPosts] = useState<CommunityPost[] | null>(null);
    const [page, setPage] = useState(1);
    const [total, setTotal] = useState(0);
    const [loadingMore, setLoadingMore] = useState(false);

    const load = useCallback(
        async (nextPage: number) => {
            const res = await api.get("/community/posts", { params: { page: nextPage, limit } });
            const data = res.data?.data;
            return { posts: (data?.posts ?? []) as CommunityPost[], total: Number(data?.total ?? 0) };
        },
        [limit],
    );

    useEffect(() => {
        let cancelled = false;
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

    const share = async (post: CommunityPost) => {
        const url = `${window.location.origin}/cong-dong#${post.id}`;
        try {
            if (navigator.share) {
                await navigator.share({ title: post.title || post.authorName, url });
            } else {
                await navigator.clipboard.writeText(url);
                toast.success("Đã sao chép liên kết bài viết");
            }
        } catch {
            // Người dùng huỷ chia sẻ.
        }
    };

    const hasMore = posts !== null && posts.length < total;

    return (
        <section className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm overflow-hidden">
            <div className="relative px-4 py-3.5 flex items-center justify-between border-b border-slate-200/80 dark:border-slate-800">
                <span className="absolute left-0 top-3.5 bottom-3.5 w-1 rounded-r bg-violet-500" aria-hidden="true" />
                <div className="flex items-center gap-3">
                    <span className="w-9 h-9 rounded-xl bg-violet-500/10 text-violet-600 dark:text-violet-400 flex items-center justify-center">
                        <MessagesSquare className="w-[18px] h-[18px]" />
                    </span>
                    <div>
                        <h2 className="font-bold text-[15px] leading-tight text-slate-900 dark:text-white">Thảo luận</h2>
                        <p className="text-xs text-slate-500 dark:text-slate-400">Góc nhìn cộng đồng</p>
                    </div>
                </div>
                <Link
                    href="/cong-dong"
                    className="inline-flex items-center gap-1 text-xs font-semibold text-blue-600 dark:text-blue-400 hover:underline"
                >
                    Toàn bộ <ArrowRight className="w-3.5 h-3.5" />
                </Link>
            </div>

            {posts === null ? (
                <div className="p-4 space-y-4">
                    {Array.from({ length: 3 }).map((_, i) => (
                        <div key={i} className="h-32 rounded-xl bg-slate-100 dark:bg-slate-800 animate-pulse" />
                    ))}
                </div>
            ) : posts.length === 0 ? (
                <p className="p-5 text-center text-sm text-slate-500 dark:text-slate-400">
                    Chưa có thảo luận nào.{" "}
                    <Link href="/cong-dong" className="text-blue-600 dark:text-blue-400 font-semibold">
                        Đăng bài đầu tiên
                    </Link>
                </p>
            ) : (
                <div className="divide-y divide-slate-200/80 dark:divide-slate-800">
                    {posts.map((post) => {
                        const href = `/cong-dong#${post.id}`;
                        const symbols = postSymbols(post);
                        return (
                            <article key={post.id} className="px-4 pt-4">
                                <div className="flex items-center gap-3">
                                    <UserAvatar src={post.authorAvatar} name={post.authorName} size={40} className="shrink-0" />
                                    <div className="min-w-0 flex-1">
                                        <p className="text-[15px] font-bold text-slate-900 dark:text-slate-100 truncate">
                                            {post.authorName}
                                        </p>
                                        <p className="text-xs text-slate-500 dark:text-slate-400">
                                            {formatRelativeTime(post.createdAt)}
                                        </p>
                                    </div>
                                    <Link
                                        href={href}
                                        aria-label="Mở bài viết"
                                        className="p-1.5 -mr-1.5 rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
                                    >
                                        <MoreHorizontal className="w-5 h-5" />
                                    </Link>
                                </div>

                                {/* div thay cho Link vì nội dung có thể chứa thẻ <a> (link trong bài) */}
                                <div
                                    role="link"
                                    tabIndex={0}
                                    onClick={() => router.push(href)}
                                    onKeyDown={(e) => e.key === "Enter" && router.push(href)}
                                    className="block mt-3 cursor-pointer"
                                >
                                    {post.title && (
                                        <p className="text-sm font-semibold text-slate-900 dark:text-slate-100 line-clamp-2 wrap-anywhere mb-1">
                                            {post.title}
                                        </p>
                                    )}
                                    <p className="text-sm leading-6 text-slate-700 dark:text-slate-300 whitespace-pre-line line-clamp-5 wrap-anywhere">
                                        {renderContent(post.content)}
                                    </p>
                                    {post.imageUrl && (
                                        // eslint-disable-next-line @next/next/no-img-element
                                        <img
                                            src={post.imageUrl}
                                            alt=""
                                            loading="lazy"
                                            onError={(e) => (e.currentTarget.style.display = "none")}
                                            className="mt-3 w-full max-h-48 object-cover rounded-xl"
                                        />
                                    )}
                                </div>

                                {symbols.length > 0 && (
                                    <div className="mt-3 flex flex-wrap items-center gap-2">
                                        {symbols.slice(0, MAX_CHIPS).map((symbol) => (
                                            <Link
                                                key={symbol}
                                                href={`/ma-chung-khoan/${symbol.toLowerCase()}`}
                                                className="px-3 py-1.5 rounded-xl bg-slate-100 dark:bg-slate-800 text-sm font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-700"
                                            >
                                                {symbol}
                                            </Link>
                                        ))}
                                        {symbols.length > MAX_CHIPS && (
                                            <Link href={href} aria-label="Xem thêm mã" className="px-1.5 text-slate-500">
                                                <MoreHorizontal className="w-5 h-5" />
                                            </Link>
                                        )}
                                    </div>
                                )}

                                <div className="mt-3 grid grid-cols-3 border-t border-slate-200/80 dark:border-slate-800 text-sm text-slate-600 dark:text-slate-300">
                                    <button
                                        type="button"
                                        onClick={() => toggleLike(post)}
                                        className={`py-2.5 inline-flex items-center justify-center gap-1.5 cursor-pointer hover:text-blue-600 dark:hover:text-blue-400 ${
                                            post.isLiked ? "text-blue-600 dark:text-blue-400 font-semibold" : ""
                                        }`}
                                    >
                                        <ThumbsUp className="w-4 h-4" fill={post.isLiked ? "currentColor" : "none"} />
                                        Thích{post.likes > 0 ? ` ${post.likes}` : ""}
                                    </button>
                                    <Link
                                        href={href}
                                        className="py-2.5 inline-flex items-center justify-center gap-1.5 hover:text-blue-600 dark:hover:text-blue-400"
                                    >
                                        <MessageSquare className="w-4 h-4" />
                                        Bình luận{post.commentsCount > 0 ? ` ${post.commentsCount}` : ""}
                                    </Link>
                                    <button
                                        type="button"
                                        onClick={() => share(post)}
                                        className="py-2.5 inline-flex items-center justify-center gap-1.5 cursor-pointer hover:text-blue-600 dark:hover:text-blue-400"
                                    >
                                        <Share2 className="w-4 h-4" /> Chia sẻ
                                    </button>
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
                    className="w-full py-3 border-t border-slate-200/80 dark:border-slate-800 text-sm font-semibold text-blue-600 dark:text-blue-400 hover:bg-slate-50 dark:hover:bg-slate-800/60 inline-flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-60"
                >
                    {loadingMore && <Loader2 className="w-4 h-4 animate-spin" />}
                    Xem thêm thảo luận
                </button>
            )}
        </section>
    );
}
