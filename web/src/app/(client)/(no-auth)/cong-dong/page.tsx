"use client";

import React, { useState, useEffect, useMemo } from "react";
import Link from "next/link";
import Image from "next/image";
import {
    MessageSquare,
    Heart,
    Share2,
    Bookmark,
    TrendingUp,
    TrendingDown,
    Send,
    Sparkles,
    BarChart3,
    Users,
    Award,
    Flame,
    Plus,
    Search,
    ShieldCheck,
    HelpCircle,
    Compass,
    Tag,
    ArrowUpRight,
    Target,
    Trash2,
    MessageCircle,
} from "lucide-react";
import { useAuth } from "@/auth/AuthProvider";
import { useAppDispatch, useAppSelector } from "@/redux/hooks";
import { useRouter } from "next/navigation";
import UserAvatar from "@/share/components/UserAvatar";
import { Role } from "@/share/enum";
import { toast } from "react-toastify";
import {
    fetchCommunityPosts,
    createCommunityPost,
    toggleLikeCommunityPost,
    toggleSaveCommunityPost,
    addCommunityComment,
    deleteCommunityComment,
    deleteCommunityPost,
} from "@/store/community/community.api";
import {
    optimisticToggleLike,
    optimisticToggleSave,
    CommunityPost,
} from "@/store/community/community.reducer";
import { useCommunityRealtime } from "./components/CommunityRealtimeProvider";
import MessagesButton from "./components/MessagesButton";
import { formatRelativeTime } from "./components/formatRelativeTime";

// Types
export type RecommendationStance = "BUY" | "SELL" | "HOLD" | "ANALYSIS";

// Popular stock suggestions for quick tagging
const POPULAR_TICKERS = [
    { symbol: "FPT", name: "FPT Corp", price: "135.20", change: "+2.42%", isUp: true },
    { symbol: "HPG", name: "Tập đoàn Hòa Phát", price: "28.65", change: "+1.24%", isUp: true },
    { symbol: "TCB", name: "Techcombank", price: "34.80", change: "+3.10%", isUp: true },
    { symbol: "SSI", name: "Chứng khoán SSI", price: "32.15", change: "-0.46%", isUp: false },
    { symbol: "NVL", name: "Tập đoàn Novaland", price: "13.20", change: "-1.85%", isUp: false },
    { symbol: "VHM", name: "Vinhomes", price: "41.50", change: "+0.73%", isUp: true },
];

const TOP_CONTRIBUTORS = [
    { name: "Vũ Tuấn Anh - CFA", role: "Phân tích Kỹ thuật", badge: "Chuyên gia", isFollowed: true },
    { name: "FinSight AI Analyst", role: "Trợ lý Phân tích AI", badge: "AI Analyst", isFollowed: true },
    { name: "Hoàng Yến Nhi", role: "Nhà đầu tư Cá nhân", badge: "VIP Trader", isFollowed: false },
    { name: "Phạm Hải Đăng", role: "Tư vấn Đầu tư", badge: "Thành viên", isFollowed: false },
];

export default function CommunityPage() {
    const dispatch = useAppDispatch();
    const router = useRouter();
    const { user, isAuthenticated } = useAuth();
    const { posts, loading } = useAppSelector((state) => state.community);
    const { connected } = useCommunityRealtime();

    // State for posts
    const [activeTab, setActiveTab] = useState<string>("all");
    const [selectedSector, setSelectedSector] = useState<string>("all");
    const [searchKeyword, setSearchKeyword] = useState<string>("");
    const [debouncedKeyword, setDebouncedKeyword] = useState<string>("");

    // State for creating a new post
    const [newPostContent, setNewPostContent] = useState<string>("");
    const [newPostSymbol, setNewPostSymbol] = useState<string>("");
    const [newPostStance, setNewPostStance] = useState<RecommendationStance>("BUY");
    const [newPostTarget, setNewPostTarget] = useState<string>("");
    const [newPostStopLoss, setNewPostStopLoss] = useState<string>("");
    const [isPostingOpen, setIsPostingOpen] = useState<boolean>(false);
    const [showTargetInputs, setShowTargetInputs] = useState<boolean>(false);

    // State for commenting
    const [activeCommentPostId, setActiveCommentPostId] = useState<string | null>(null);
    const [commentText, setCommentText] = useState<string>("");

    // Market Sentiment Poll State
    const [pollVote, setPollVote] = useState<"bull" | "bear" | "sideway" | null>(null);
    const [pollVotes, setPollVotes] = useState({ bull: 68, bear: 22, sideway: 10 });

    useEffect(() => {
        const timer = setTimeout(() => setDebouncedKeyword(searchKeyword.trim()), 350);
        return () => clearTimeout(timer);
    }, [searchKeyword]);

    // Refetch when the filters change, and when the viewer changes so the
    // "liked/saved by me" flags match the signed-in account.
    useEffect(() => {
        dispatch(
            fetchCommunityPosts({
                category: activeTab !== "all" ? activeTab : undefined,
                sector: selectedSector !== "all" ? selectedSector : undefined,
                keyword: debouncedKeyword || undefined,
            })
        );
    }, [dispatch, user?.id, activeTab, selectedSector, debouncedKeyword]);

    // Load poll vote from localStorage
    useEffect(() => {
        try {
            const savedVote = localStorage.getItem("fireant_poll_vote");
            if (savedVote === "bull" || savedVote === "bear" || savedVote === "sideway") {
                setPollVote(savedVote);
            }
        } catch {
            // Ignore parse errors
        }
    }, []);

    // Handle Creating New Post
    const handleCreatePost = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!newPostContent.trim()) {
            toast.warning("Vui lòng nhập nội dung nhận định!");
            return;
        }

        if (!isAuthenticated) {
            toast.info("Vui lòng đăng nhập để đăng bài viết thảo luận!");
            router.push("/login");
            return;
        }

        const symbol = newPostSymbol.trim().toUpperCase();
        const target = parseFloat(newPostTarget) || undefined;
        const stopLoss = parseFloat(newPostStopLoss) || undefined;

        try {
            await dispatch(
                createCommunityPost({
                    content: newPostContent.trim(),
                    symbol: symbol || undefined,
                    stance: symbol ? newPostStance : "ANALYSIS",
                    targetPrice: target,
                    stopLossPrice: stopLoss,
                    category: symbol && (target || stopLoss) ? "signal" : "hot",
                })
            ).unwrap();

            // Reset composer
            setNewPostContent("");
            setNewPostSymbol("");
            setNewPostTarget("");
            setNewPostStopLoss("");
            setShowTargetInputs(false);
            setIsPostingOpen(false);
            toast.success("Đã đăng bài thảo luận thành công!");
        } catch (err) {
            toast.error(typeof err === "string" ? err : "Không thể đăng bài viết");
        }
    };

    // Handle Toggling Like on a Post
    const handleToggleLike = (postId: string) => {
        if (!isAuthenticated) {
            toast.info("Vui lòng đăng nhập để thả tim bài viết!");
            router.push("/login");
            return;
        }

        dispatch(optimisticToggleLike({ postId }));
        dispatch(toggleLikeCommunityPost(postId));
    };

    // Handle Toggling Bookmark on a Post
    const handleToggleSave = (postId: string) => {
        if (!isAuthenticated) {
            toast.info("Vui lòng đăng nhập để lưu bài viết quan tâm!");
            router.push("/login");
            return;
        }

        dispatch(optimisticToggleSave({ postId }));
        dispatch(toggleSaveCommunityPost(postId))
            .unwrap()
            .then((res) => {
                toast.info(res?.isSaved ? "Đã lưu bài viết vào danh sách quan tâm" : "Đã hủy lưu bài viết");
            });
    };

    // Handle Sharing Post Link
    const handleSharePost = (post: CommunityPost) => {
        if (typeof window !== "undefined") {
            const url = `${window.location.origin}/cong-dong#${post.id}`;
            navigator.clipboard?.writeText(url).then(() => {
                toast.success("Đã sao chép liên kết bài viết vào clipboard!");
            });
        }
    };

    // Handle Adding a Comment
    const handleAddComment = async (postId: string) => {
        if (!commentText.trim()) return;

        if (!isAuthenticated) {
            toast.info("Vui lòng đăng nhập để gửi bình luận!");
            router.push("/login");
            return;
        }

        try {
            await dispatch(
                addCommunityComment({ postId, content: commentText.trim() })
            ).unwrap();

            setCommentText("");
            toast.success("Đã gửi bình luận thành công!");
        } catch (err) {
            toast.error(typeof err === "string" ? err : "Không thể gửi bình luận");
        }
    };

    // Handle Deleting Post (Owner or Admin)
    const handleDeletePost = (postId: string) => {
        if (!isAuthenticated) {
            toast.info("Vui lòng đăng nhập!");
            router.push("/login");
            return;
        }

        if (window.confirm("Bạn có chắc chắn muốn xóa bài viết này không?")) {
            dispatch(deleteCommunityPost(postId))
                .unwrap()
                .then(() => {
                    toast.success("Đã xóa bài viết thành công!");
                })
                .catch((err) => {
                    toast.error(typeof err === "string" ? err : "Không thể xóa bài viết");
                });
        }
    };

    const handleDeleteComment = (postId: string, commentId: string) => {
        if (!window.confirm("Xóa bình luận này?")) return;
        dispatch(deleteCommunityComment({ postId, commentId }))
            .unwrap()
            .then(() => toast.success("Đã xóa bình luận"))
            .catch((err) => toast.error(typeof err === "string" ? err : "Không thể xóa bình luận"));
    };

    const handleMessageAuthor = (authorId: number) => {
        if (!isAuthenticated) {
            toast.info("Vui lòng đăng nhập để nhắn tin!");
            router.push("/login");
            return;
        }
        router.push(`/cong-dong/tin-nhan?userId=${authorId}`);
    };

    const canModify = (ownerId?: number | null) =>
        user?.role === Role.Admin || (!!user?.id && ownerId === user.id);

    // Handle Market Sentiment Poll Vote
    const handleVotePoll = (type: "bull" | "bear" | "sideway") => {
        if (pollVote) {
            toast.info("Bạn đã tham gia bình chọn khảo sát hôm nay!");
            return;
        }
        setPollVote(type);
        setPollVotes((prev) => ({
            ...prev,
            [type]: prev[type] + 1,
        }));
        try {
            localStorage.setItem("fireant_poll_vote", type);
        } catch {}
        toast.success("Cảm ơn bạn đã tham gia khảo sát thị trường!");
    };

    // Filter Posts
    const filteredPosts = useMemo(() => {
        return posts.filter((post) => {
            // Tab filter
            if (activeTab === "hot" && post.category !== "hot" && post.likes < 50) return false;
            if (activeTab === "signal" && post.category !== "signal" && !post.stance) return false;
            if (activeTab === "technical" && post.category !== "technical") return false;
            if (activeTab === "fundamental" && post.category !== "fundamental") return false;
            if (activeTab === "qa" && post.category !== "qa") return false;
            if (activeTab === "saved" && !post.isSaved) return false;

            // Sector filter
            if (selectedSector !== "all" && post.sector !== selectedSector) return false;

            // Search filter
            if (searchKeyword.trim()) {
                const kw = searchKeyword.toLowerCase();
                const matchTitle = post.title?.toLowerCase().includes(kw);
                const matchContent = post.content.toLowerCase().includes(kw);
                const matchSymbol = post.symbol?.toLowerCase().includes(kw);
                const matchAuthor = post.authorName.toLowerCase().includes(kw);
                if (!matchTitle && !matchContent && !matchSymbol && !matchAuthor) return false;
            }

            return true;
        });
    }, [posts, activeTab, selectedSector, searchKeyword]);

    const totalPollCount = pollVotes.bull + pollVotes.bear + pollVotes.sideway;
    const bullPercent = Math.round((pollVotes.bull / totalPollCount) * 100);
    const bearPercent = Math.round((pollVotes.bear / totalPollCount) * 100);
    const sidewayPercent = 100 - bullPercent - bearPercent;

    return (
        <div className="min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 transition-colors duration-200">
            {/* 1. Header Banner */}
            <div className="bg-gradient-to-r from-blue-900 via-indigo-900 to-slate-900 text-white border-b border-indigo-950/60 py-6 px-4">
                <div className="max-w-[1400px] mx-auto flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                    <div>
                        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/10 backdrop-blur-md text-xs font-semibold text-blue-200 mb-2">
                            <Users size={14} className="text-blue-400" />
                            <span>Diễn đàn & Mạng xã hội Nhà đầu tư</span>
                        </div>
                        <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight">
                            Cộng đồng Đầu tư Chứng khoán FinSight
                        </h1>
                        <p className="text-slate-300 text-xs sm:text-sm mt-1 max-w-2xl">
                            Không gian trao đổi góc nhìn phân tích, thảo luận tín hiệu kỹ thuật và chia sẻ kinh nghiệm đầu tư thực chiến.
                        </p>
                    </div>

                    <div className="flex items-center gap-2 self-start sm:self-auto">
                        {isAuthenticated && <MessagesButton />}
                        <button
                            type="button"
                            onClick={() => {
                                setIsPostingOpen(true);
                                window.scrollTo({ top: 180, behavior: "smooth" });
                            }}
                            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs sm:text-sm shadow-md transition-all shrink-0 cursor-pointer"
                        >
                            <Plus size={16} />
                            <span>Tạo bài thảo luận</span>
                        </button>
                    </div>
                </div>
            </div>

            {/* 2. Main Container with 3-Column Layout */}
            <div className="max-w-[1400px] mx-auto px-4 py-6">
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
                    {/* LEFT COLUMN: Channels & Categories (Hidden on mobile, col-span-3) */}
                    <div className="hidden lg:block lg:col-span-3 space-y-4 sticky top-20">
                        {/* Channel list */}
                        <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 p-4 shadow-sm">
                            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500 mb-3 flex items-center gap-2">
                                <Compass size={14} className="text-blue-500" />
                                <span>Chủ đề thảo luận</span>
                            </h3>

                            <div className="space-y-1">
                                {[
                                    { id: "all", label: "Tất cả bài viết", icon: Sparkles, color: "text-blue-500" },
                                    { id: "hot", label: "Thảo luận Nổi bật", icon: Flame, color: "text-rose-500" },
                                    { id: "signal", label: "Tín hiệu & Khuyến nghị", icon: Target, color: "text-emerald-500" },
                                    { id: "technical", label: "Phân tích Kỹ thuật", icon: BarChart3, color: "text-indigo-500" },
                                    { id: "fundamental", label: "Doanh nghiệp & BCTC", icon: BuildingIcon, color: "text-amber-500" },
                                    { id: "qa", label: "Hỏi đáp & Chia sẻ", icon: HelpCircle, color: "text-cyan-500" },
                                ].map((tab) => {
                                    const Icon = tab.icon;
                                    const isActive = activeTab === tab.id;
                                    return (
                                        <button
                                            key={tab.id}
                                            onClick={() => setActiveTab(tab.id)}
                                            className={`w-full flex items-center justify-between px-3 py-2.5 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
                                                isActive
                                                    ? "bg-blue-50 dark:bg-blue-950/60 text-blue-600 dark:text-blue-400 shadow-xs font-bold"
                                                    : "text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800/60"
                                            }`}
                                        >
                                            <div className="flex items-center gap-2.5 min-w-0">
                                                <Icon size={16} className={`shrink-0 ${tab.color}`} />
                                                <span className="truncate">{tab.label}</span>
                                            </div>
                                            {isActive && <div className="w-1.5 h-1.5 rounded-full bg-blue-500 shrink-0" />}
                                        </button>
                                    );
                                })}
                            </div>

                            {/* Saved posts filter */}
                            <div className="mt-4 pt-3 border-t border-slate-100 dark:border-slate-800">
                                <button
                                    onClick={() => {
                                        if (!isAuthenticated) {
                                            toast.info("Vui lòng đăng nhập để xem danh sách bài viết đã lưu!");
                                            router.push("/login");
                                            return;
                                        }
                                        setActiveTab("saved");
                                    }}
                                    className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
                                        activeTab === "saved"
                                            ? "bg-amber-50 dark:bg-amber-950/60 text-amber-600 dark:text-amber-400"
                                            : "text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800/60"
                                    }`}
                                >
                                    <Bookmark size={15} className="text-amber-500" />
                                    <span>Bài viết đã lưu ({posts.filter((p) => p.isSaved).length})</span>
                                </button>
                            </div>
                        </div>

                        {/* Sector filters */}
                        <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 p-4 shadow-sm">
                            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500 mb-3 flex items-center gap-2">
                                <Tag size={14} className="text-emerald-500" />
                                <span>Lọc theo Nhóm ngành</span>
                            </h3>

                            <div className="flex flex-wrap gap-1.5">
                                {["all", "Công nghệ", "Ngân hàng", "Thép", "Bất động sản", "Chứng khoán", "Bán lẻ"].map((sec) => (
                                    <button
                                        key={sec}
                                        onClick={() => setSelectedSector(sec)}
                                        className={`px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer ${
                                            selectedSector === sec
                                                ? "bg-slate-900 dark:bg-white text-white dark:text-slate-900 font-semibold"
                                                : "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700"
                                        }`}
                                    >
                                        {sec === "all" ? "Tất cả ngành" : sec}
                                    </button>
                                ))}
                            </div>
                        </div>
                    </div>

                    {/* MIDDLE COLUMN: Post Composer + Feed (col-span-6 on Desktop) */}
                    <div className="lg:col-span-6 min-w-0 space-y-4">
                        {/* Search Box on Mobile/Tablet */}
                        <div className="relative">
                            <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
                            <input
                                type="text"
                                placeholder="Tìm kiếm bài viết, mã cổ phiếu ($FPT, $HPG) hoặc tác giả..."
                                value={searchKeyword}
                                onChange={(e) => setSearchKeyword(e.target.value)}
                                className="w-full pl-9 pr-4 py-2.5 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 text-xs sm:text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/50 transition-all shadow-xs"
                            />
                            {searchKeyword && (
                                <button
                                    onClick={() => setSearchKeyword("")}
                                    className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
                                >
                                    Xóa
                                </button>
                            )}
                        </div>

                        {/* Interactive Post Composer */}
                        <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 p-4 shadow-sm transition-all">
                            <div className="flex items-start gap-3">
                                <UserAvatar
                                    src={user?.avatar}
                                    name={user?.fullName || user?.username || "User"}
                                    size={40}
                                    className="shrink-0"
                                />

                                <div className="flex-1 min-w-0">
                                    <textarea
                                        rows={isPostingOpen ? 4 : 2}
                                        placeholder={
                                            isAuthenticated
                                                ? `Chào ${user?.fullName || user?.username || "bạn"}, hôm nay bạn có nhận định gì về thị trường? Gõ $MÃ để tag cổ phiếu...`
                                                : "Đăng nhập để chia sẻ nhận định và thảo luận cùng cộng đồng..."
                                        }
                                        value={newPostContent}
                                        onFocus={() => setIsPostingOpen(true)}
                                        onChange={(e) => setNewPostContent(e.target.value)}
                                        className="w-full resize-none bg-slate-50 dark:bg-slate-800/70 rounded-xl p-3 text-xs sm:text-sm border border-slate-200/60 dark:border-slate-700/60 focus:outline-none focus:ring-2 focus:ring-blue-500/50 transition-all placeholder:text-slate-400"
                                    />

                                    {/* Expanded Composer Options */}
                                    {isPostingOpen && (
                                        <div className="mt-3 space-y-3 animate-fadeIn">
                                            {/* Tag Ticker & Stance */}
                                            <div className="flex flex-wrap items-center gap-2">
                                                <div className="flex items-center gap-1.5 bg-slate-100 dark:bg-slate-800 px-2.5 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700">
                                                    <span className="text-xs font-bold text-blue-600 dark:text-blue-400">$</span>
                                                    <input
                                                        type="text"
                                                        placeholder="Mã CP (FPT, HPG...)"
                                                        value={newPostSymbol}
                                                        onChange={(e) => setNewPostSymbol(e.target.value.toUpperCase())}
                                                        className="w-24 uppercase bg-transparent text-xs font-bold focus:outline-none placeholder:font-normal placeholder:text-slate-400"
                                                    />
                                                </div>

                                                {/* Stance Selector */}
                                                <div className="flex items-center gap-1 bg-slate-100 dark:bg-slate-800 p-1 rounded-lg">
                                                    {[
                                                        { id: "BUY", label: "🟢 Mua", color: "hover:text-emerald-500" },
                                                        { id: "SELL", label: "🔴 Bán", color: "hover:text-rose-500" },
                                                        { id: "HOLD", label: "🟡 Quan sát", color: "hover:text-amber-500" },
                                                        { id: "ANALYSIS", label: "📊 Phân tích", color: "hover:text-blue-500" },
                                                    ].map((item) => (
                                                        <button
                                                            key={item.id}
                                                            type="button"
                                                            onClick={() => setNewPostStance(item.id as RecommendationStance)}
                                                            className={`px-2 py-1 rounded-md text-xs font-semibold transition-all cursor-pointer ${
                                                                newPostStance === item.id
                                                                    ? "bg-white dark:bg-slate-700 shadow-xs text-blue-600 dark:text-blue-400"
                                                                    : "text-slate-500 dark:text-slate-400"
                                                            }`}
                                                        >
                                                            {item.label}
                                                        </button>
                                                    ))}
                                                </div>

                                                {/* Toggle Target Price & Stop Loss Inputs */}
                                                <button
                                                    type="button"
                                                    onClick={() => setShowTargetInputs(!showTargetInputs)}
                                                    className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1 transition-colors cursor-pointer ${
                                                        showTargetInputs
                                                            ? "bg-blue-100 dark:bg-blue-950/80 text-blue-600 dark:text-blue-400"
                                                            : "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200"
                                                    }`}
                                                >
                                                    <Target size={13} />
                                                    <span>Target & Cắt lỗ</span>
                                                </button>
                                            </div>

                                            {/* Target Price & Stoploss inputs */}
                                            {showTargetInputs && (
                                                <div className="grid grid-cols-2 gap-2 p-2.5 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 text-xs animate-fadeIn">
                                                    <div>
                                                        <label className="block text-[11px] font-semibold text-emerald-600 dark:text-emerald-400 mb-1">
                                                            Giá mục tiêu (Target)
                                                        </label>
                                                        <input
                                                            type="number"
                                                            step="0.1"
                                                            placeholder="VD: 145.0"
                                                            value={newPostTarget}
                                                            onChange={(e) => setNewPostTarget(e.target.value)}
                                                            className="w-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg px-2.5 py-1.5 font-mono focus:outline-none focus:ring-1 focus:ring-emerald-500"
                                                        />
                                                    </div>
                                                    <div>
                                                        <label className="block text-[11px] font-semibold text-rose-600 dark:text-rose-400 mb-1">
                                                            Giá cắt lỗ (Stop Loss)
                                                        </label>
                                                        <input
                                                            type="number"
                                                            step="0.1"
                                                            placeholder="VD: 125.0"
                                                            value={newPostStopLoss}
                                                            onChange={(e) => setNewPostStopLoss(e.target.value)}
                                                            className="w-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg px-2.5 py-1.5 font-mono focus:outline-none focus:ring-1 focus:ring-rose-500"
                                                        />
                                                    </div>
                                                </div>
                                            )}

                                            {/* Actions & Submit */}
                                            <div className="flex items-center justify-between pt-2 border-t border-slate-100 dark:border-slate-800">
                                                <div className="flex items-center gap-2 text-slate-400 text-xs">
                                                    <span className="text-[11px]">Gợi ý: Gắn mã CP để nhận tương tác tốt hơn</span>
                                                </div>

                                                <div className="flex items-center gap-2">
                                                    <button
                                                        type="button"
                                                        onClick={() => setIsPostingOpen(false)}
                                                        className="px-3 py-1.5 text-xs text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 cursor-pointer"
                                                    >
                                                        Hủy
                                                    </button>
                                                    <button
                                                        type="button"
                                                        onClick={handleCreatePost}
                                                        className="px-4 py-1.5 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white text-xs font-semibold rounded-xl shadow-xs transition-all flex items-center gap-1.5 cursor-pointer"
                                                    >
                                                        <Send size={13} />
                                                        <span>Đăng bài</span>
                                                    </button>
                                                </div>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>

                        {/* Mobile Category Filter Bar */}
                        <div className="lg:hidden flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-none">
                            {[
                                { id: "all", label: "Tất cả" },
                                { id: "hot", label: "Nổi bật" },
                                { id: "signal", label: "Khuyến nghị" },
                                { id: "technical", label: "Phân tích KT" },
                                { id: "fundamental", label: "BCTC & Doanh nghiệp" },
                                { id: "qa", label: "Hỏi đáp" },
                            ].map((tab) => (
                                <button
                                    key={tab.id}
                                    onClick={() => setActiveTab(tab.id)}
                                    className={`px-3 py-1.5 rounded-full text-xs font-semibold shrink-0 cursor-pointer ${
                                        activeTab === tab.id
                                            ? "bg-blue-600 text-white"
                                            : "bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-300"
                                    }`}
                                >
                                    {tab.label}
                                </button>
                            ))}
                        </div>

                        {/* Feed Count */}
                        <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400 px-1">
                            <span>Hiển thị {filteredPosts.length} bài thảo luận</span>
                            <span className="flex items-center gap-1.5">
                                <span
                                    className={`w-2 h-2 rounded-full ${connected ? "bg-emerald-500 animate-pulse" : "bg-slate-400"}`}
                                />
                                {connected ? "Cập nhật theo thời gian thực" : "Đang kết nối máy chủ realtime..."}
                            </span>
                        </div>

                        {/* Post Feed List */}
                        <div className="space-y-4">
                            {loading && posts.length === 0 ? (
                                <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-10 text-center text-slate-500">
                                    <div className="w-8 h-8 border-3 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                                    <p className="font-semibold text-sm">Đang tải các bài thảo luận từ cộng đồng...</p>
                                </div>
                            ) : filteredPosts.length === 0 ? (
                                <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-10 text-center text-slate-500">
                                    <MessageSquare size={36} className="mx-auto mb-2 text-slate-300 dark:text-slate-700" />
                                    <p className="font-semibold text-sm">Chưa có bài thảo luận nào phù hợp</p>
                                    <p className="text-xs text-slate-400 mt-1">Hãy là người đầu tiên chia sẻ nhận định về chủ đề này!</p>
                                </div>
                            ) : (
                                filteredPosts.map((post) => {
                                    const isCommentsOpen = activeCommentPostId === post.id;

                                    return (
                                        <article
                                            key={post.id}
                                            id={post.id}
                                            className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 p-4 sm:p-5 shadow-sm hover:shadow-md transition-all duration-200"
                                        >
                                            {/* Post Header: Author + Badges */}
                                            <div className="flex items-start justify-between gap-3 mb-3">
                                                <div className="flex items-center gap-3 min-w-0">
                                                    <UserAvatar
                                                        src={post.authorAvatar}
                                                        name={post.authorName}
                                                        size={42}
                                                        className="shrink-0"
                                                    />
                                                    <div className="min-w-0">
                                                        <div className="flex items-center gap-2 flex-wrap">
                                                            <h4 className="font-bold text-sm text-slate-900 dark:text-white truncate">
                                                                {post.authorName}
                                                            </h4>
                                                            {post.authorBadge && (
                                                                <span
                                                                    className={`px-2 py-0.5 rounded-full text-[10px] font-extrabold tracking-wide uppercase ${
                                                                        post.authorBadge === "Chuyên gia"
                                                                            ? "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300 border border-blue-200 dark:border-blue-800"
                                                                            : post.authorBadge === "AI Analyst"
                                                                              ? "bg-purple-100 text-purple-700 dark:bg-purple-950 dark:text-purple-300 border border-purple-200 dark:border-purple-800"
                                                                              : post.authorBadge === "VIP Trader"
                                                                                ? "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300 border border-amber-200 dark:border-amber-800"
                                                                                : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400"
                                                                    }`}
                                                                >
                                                                    {post.authorBadge}
                                                                </span>
                                                            )}
                                                        </div>
                                                        <div className="flex items-center flex-wrap gap-x-2 text-xs text-slate-400 mt-0.5">
                                                            {post.authorRole && <span className="truncate">{post.authorRole}</span>}
                                                            {post.authorRole && <span>•</span>}
                                                            <span className="whitespace-nowrap">{formatRelativeTime(post.createdAt)}</span>
                                                        </div>
                                                    </div>
                                                </div>

                                                {/* Header Right Actions: Symbol Badge & Delete Button */}
                                                <div className="flex items-center gap-2 shrink-0">
                                                    {post.symbol && (
                                                        <div className="flex flex-col items-end gap-1">
                                                            <Link
                                                                href={`/ma-chung-khoan/${post.symbol.toLowerCase()}`}
                                                                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-blue-50 dark:bg-blue-950/70 border border-blue-200 dark:border-blue-800 text-blue-700 dark:text-blue-300 font-bold text-xs hover:scale-105 transition-transform"
                                                            >
                                                                <span>${post.symbol}</span>
                                                                <ArrowUpRight size={13} />
                                                            </Link>
                                                            {post.stance && (
                                                                <span
                                                                    className={`text-[10px] font-extrabold px-1.5 py-0.5 rounded whitespace-nowrap ${
                                                                        post.stance === "BUY"
                                                                            ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                                                                            : post.stance === "SELL"
                                                                              ? "bg-rose-500/10 text-rose-600 dark:text-rose-400"
                                                                              : "bg-amber-500/10 text-amber-600 dark:text-amber-400"
                                                                    }`}
                                                                >
                                                                    {post.stance === "BUY"
                                                                        ? "🟢 KHUYẾN NGHỊ MUA"
                                                                        : post.stance === "SELL"
                                                                          ? "🔴 KHUYẾN NGHỊ BÁN"
                                                                          : "🟡 THEO DÕI"}
                                                                </span>
                                                            )}
                                                        </div>
                                                    )}

                                                    {post.userId && post.userId !== user?.id && (
                                                        <button
                                                            type="button"
                                                            onClick={() => handleMessageAuthor(post.userId!)}
                                                            className="p-1.5 rounded-lg text-slate-400 hover:text-blue-600 dark:hover:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-950/50 transition-colors cursor-pointer"
                                                            title={`Nhắn tin cho ${post.authorName}`}
                                                        >
                                                            <MessageCircle size={16} />
                                                        </button>
                                                    )}

                                                    {/* Delete Button (Allowed for post author or admin) */}
                                                    {canModify(post.userId) && (
                                                        <button
                                                            type="button"
                                                            onClick={(e) => {
                                                                e.stopPropagation();
                                                                handleDeletePost(post.id);
                                                            }}
                                                            className="p-1.5 rounded-lg text-slate-400 hover:text-rose-600 dark:hover:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/50 transition-colors cursor-pointer"
                                                            title="Xóa bài viết này"
                                                        >
                                                            <Trash2 size={16} />
                                                        </button>
                                                    )}
                                                </div>
                                            </div>

                                            {/* Post Title */}
                                            {post.title && (
                                                <h3 className="text-base font-bold text-slate-900 dark:text-slate-100 mb-2 leading-snug wrap-anywhere">
                                                    {post.title}
                                                </h3>
                                            )}

                                            {/* Post Content */}
                                            <p className="text-xs sm:text-sm text-slate-700 dark:text-slate-300 leading-relaxed whitespace-pre-line wrap-anywhere mb-3">
                                                {post.content}
                                            </p>

                                            {/* Target Price & Stoploss Box if available */}
                                            {(post.targetPrice || post.stopLossPrice) && (
                                                <div className="flex items-center gap-4 p-2.5 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200/80 dark:border-slate-700/60 text-xs font-mono mb-3">
                                                    {post.targetPrice && (
                                                        <div className="flex items-center gap-1.5">
                                                            <span className="text-slate-400 font-sans">Target:</span>
                                                            <span className="font-bold text-emerald-600 dark:text-emerald-400">
                                                                {post.targetPrice.toFixed(2)}k
                                                            </span>
                                                        </div>
                                                    )}
                                                    {post.stopLossPrice && (
                                                        <div className="flex items-center gap-1.5 border-l border-slate-200 dark:border-slate-700 pl-4">
                                                            <span className="text-slate-400 font-sans">Cắt lỗ:</span>
                                                            <span className="font-bold text-rose-600 dark:text-rose-400">
                                                                {post.stopLossPrice.toFixed(2)}k
                                                            </span>
                                                        </div>
                                                    )}
                                                </div>
                                            )}

                                            {/* Attached Image if any */}
                                            {post.imageUrl && <PostImage src={post.imageUrl} />}

                                            {/* Post Footer Action Bar */}
                                            <div className="flex items-center justify-between pt-3 border-t border-slate-100 dark:border-slate-800/80 text-xs text-slate-500 dark:text-slate-400">
                                                {/* Left actions: Like, Comment, Share */}
                                                <div className="flex items-center gap-4 sm:gap-6">
                                                    <button
                                                        type="button"
                                                        onClick={() => handleToggleLike(post.id)}
                                                        className={`flex items-center gap-1.5 transition-colors cursor-pointer font-semibold ${
                                                            post.isLiked
                                                                ? "text-rose-500 dark:text-rose-400"
                                                                : "hover:text-rose-500 dark:hover:text-rose-400"
                                                        }`}
                                                    >
                                                        <Heart
                                                            size={16}
                                                            className={post.isLiked ? "fill-rose-500 text-rose-500" : ""}
                                                        />
                                                        <span>{post.likes}</span>
                                                    </button>

                                                    <button
                                                        type="button"
                                                        onClick={() =>
                                                            setActiveCommentPostId(isCommentsOpen ? null : post.id)
                                                        }
                                                        className="flex items-center gap-1.5 hover:text-blue-600 dark:hover:text-blue-400 transition-colors cursor-pointer font-semibold"
                                                    >
                                                        <MessageSquare size={16} />
                                                        <span>{post.commentsCount} bình luận</span>
                                                    </button>

                                                    <button
                                                        type="button"
                                                        onClick={() => handleSharePost(post)}
                                                        className="flex items-center gap-1.5 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors cursor-pointer"
                                                    >
                                                        <Share2 size={16} />
                                                        <span className="hidden sm:inline">Chia sẻ</span>
                                                    </button>
                                                </div>

                                                {/* Right action: Bookmark */}
                                                <button
                                                    type="button"
                                                    onClick={() => handleToggleSave(post.id)}
                                                    className={`p-1.5 rounded-lg transition-colors cursor-pointer ${
                                                        post.isSaved
                                                            ? "text-amber-500 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/50"
                                                            : "hover:text-amber-500 dark:hover:text-amber-400"
                                                    }`}
                                                    title={post.isSaved ? "Bỏ lưu bài viết" : "Lưu bài viết"}
                                                >
                                                    <Bookmark
                                                        size={16}
                                                        className={post.isSaved ? "fill-amber-500 text-amber-500" : ""}
                                                    />
                                                </button>
                                            </div>

                                            {/* Expandable Comments Drawer */}
                                            {isCommentsOpen && (
                                                <div className="mt-4 pt-4 border-t border-slate-100 dark:border-slate-800 space-y-3 animate-fadeIn">
                                                    {/* Existing comments */}
                                                    {post.comments.length > 0 ? (
                                                        <div className="space-y-2.5 max-h-64 overflow-y-auto pr-1">
                                                            {post.comments.map((cmt) => (
                                                                <div
                                                                    key={cmt.id}
                                                                    className="flex items-start gap-2.5 p-2.5 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-200/60 dark:border-slate-700/60 text-xs"
                                                                >
                                                                    <UserAvatar
                                                                        src={cmt.authorAvatar}
                                                                        name={cmt.authorName}
                                                                        size={28}
                                                                    />
                                                                    <div className="flex-1 min-w-0">
                                                                        <div className="flex items-center justify-between gap-2 mb-0.5">
                                                                            <span className="font-bold text-slate-900 dark:text-slate-100 truncate">
                                                                                {cmt.authorName}
                                                                            </span>
                                                                            <span className="flex items-center gap-1.5 text-[10px] text-slate-400">
                                                                                {formatRelativeTime(cmt.createdAt)}
                                                                                {canModify(cmt.userId) && (
                                                                                    <button
                                                                                        type="button"
                                                                                        onClick={() => handleDeleteComment(post.id, cmt.id)}
                                                                                        className="text-slate-400 hover:text-rose-600 cursor-pointer"
                                                                                        title="Xóa bình luận"
                                                                                    >
                                                                                        <Trash2 size={12} />
                                                                                    </button>
                                                                                )}
                                                                            </span>
                                                                        </div>
                                                                        <p className="text-slate-700 dark:text-slate-300 whitespace-pre-line wrap-anywhere">
                                                                            {cmt.content}
                                                                        </p>
                                                                    </div>
                                                                </div>
                                                            ))}
                                                        </div>
                                                    ) : (
                                                        <p className="text-xs text-slate-400 text-center py-2">
                                                            Chưa có bình luận nào. Hãy là người đầu tiên bình luận!
                                                        </p>
                                                    )}

                                                    {/* Comment Input */}
                                                    <div className="flex items-center gap-2 pt-2">
                                                        <UserAvatar
                                                            src={user?.avatar}
                                                            name={user?.fullName || "User"}
                                                            size={32}
                                                            className="shrink-0"
                                                        />
                                                        <input
                                                            type="text"
                                                            placeholder="Viết câu trả lời của bạn..."
                                                            value={commentText}
                                                            onChange={(e) => setCommentText(e.target.value)}
                                                            onKeyDown={(e) => {
                                                                if (e.key === "Enter") {
                                                                    handleAddComment(post.id);
                                                                }
                                                            }}
                                                            className="flex-1 bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl px-3 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                                                        />
                                                        <button
                                                            type="button"
                                                            onClick={() => handleAddComment(post.id)}
                                                            className="p-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white transition-colors cursor-pointer"
                                                        >
                                                            <Send size={14} />
                                                        </button>
                                                    </div>
                                                </div>
                                            )}
                                        </article>
                                    );
                                })
                            )}
                        </div>
                    </div>

                    {/* RIGHT COLUMN: Market Poll + Trending Tickers + Leaderboard (col-span-3 on Desktop) */}
                    <div className="lg:col-span-3 space-y-4 lg:sticky lg:top-20">
                        {/* 1. Market Sentiment Poll */}
                        <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 p-4 shadow-sm">
                            <div className="flex items-center justify-between mb-2.5">
                                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-white flex items-center gap-1.5">
                                    <BarChart3 size={15} className="text-blue-500" />
                                    <span>Khảo sát thị trường</span>
                                </h3>
                                <span className="text-[10px] text-emerald-500 font-semibold">Live Poll</span>
                            </div>

                            <p className="text-xs text-slate-600 dark:text-slate-300 font-medium mb-3">
                                Bạn dự đoán xu hướng <span className="font-bold text-blue-600 dark:text-blue-400">VN-Index</span> phiên tiếp theo sẽ thế nào?
                            </p>

                            {/* Poll Options */}
                            <div className="space-y-2 text-xs">
                                <button
                                    onClick={() => handleVotePoll("bull")}
                                    className={`w-full p-2.5 rounded-xl border flex items-center justify-between transition-all cursor-pointer ${
                                        pollVote === "bull"
                                            ? "border-emerald-500 bg-emerald-50 dark:bg-emerald-950/50 font-bold"
                                            : "border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/60"
                                    }`}
                                >
                                    <span className="flex items-center gap-2 text-emerald-600 dark:text-emerald-400 font-semibold">
                                        <TrendingUp size={15} /> Tăng điểm (Bullish)
                                    </span>
                                    <span className="font-mono font-bold text-emerald-600 dark:text-emerald-400">
                                        {bullPercent}%
                                    </span>
                                </button>

                                <button
                                    onClick={() => handleVotePoll("bear")}
                                    className={`w-full p-2.5 rounded-xl border flex items-center justify-between transition-all cursor-pointer ${
                                        pollVote === "bear"
                                            ? "border-rose-500 bg-rose-50 dark:bg-rose-950/50 font-bold"
                                            : "border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/60"
                                    }`}
                                >
                                    <span className="flex items-center gap-2 text-rose-600 dark:text-rose-400 font-semibold">
                                        <TrendingDown size={15} /> Giảm điểm (Bearish)
                                    </span>
                                    <span className="font-mono font-bold text-rose-600 dark:text-rose-400">
                                        {bearPercent}%
                                    </span>
                                </button>

                                <button
                                    onClick={() => handleVotePoll("sideway")}
                                    className={`w-full p-2.5 rounded-xl border flex items-center justify-between transition-all cursor-pointer ${
                                        pollVote === "sideway"
                                            ? "border-amber-500 bg-amber-50 dark:bg-amber-950/50 font-bold"
                                            : "border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/60"
                                    }`}
                                >
                                    <span className="flex items-center gap-2 text-amber-600 dark:text-amber-400 font-semibold">
                                        <Compass size={15} /> Đi ngang (Sideway)
                                    </span>
                                    <span className="font-mono font-bold text-amber-600 dark:text-amber-400">
                                        {sidewayPercent}%
                                    </span>
                                </button>
                            </div>

                            <div className="mt-3 pt-2.5 border-t border-slate-100 dark:border-slate-800 text-[11px] text-slate-400 text-center">
                                Đã có {totalPollCount} nhà đầu tư bình chọn
                            </div>
                        </div>

                        {/* 2. Top Trending Tickers */}
                        <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 p-4 shadow-sm">
                            <div className="flex items-center justify-between mb-3">
                                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-white flex items-center gap-1.5">
                                    <Flame size={15} className="text-rose-500" />
                                    <span>Top Cổ phiếu được thảo luận</span>
                                </h3>
                            </div>

                            <div className="divide-y divide-slate-100 dark:divide-slate-800/60">
                                {POPULAR_TICKERS.map((ticker, index) => (
                                    <Link
                                        key={ticker.symbol}
                                        href={`/ma-chung-khoan/${ticker.symbol.toLowerCase()}`}
                                        className="py-2.5 flex items-center justify-between group hover:bg-slate-50 dark:hover:bg-slate-800/40 px-1 rounded-lg transition-colors"
                                    >
                                        <div className="flex items-center gap-2.5">
                                            <span className="text-xs font-bold font-mono text-slate-400 w-4">
                                                0{index + 1}
                                            </span>
                                            <div>
                                                <p className="font-bold text-xs text-blue-600 dark:text-blue-400 group-hover:underline">
                                                    ${ticker.symbol}
                                                </p>
                                                <p className="text-[10px] text-slate-400 truncate max-w-[110px]">{ticker.name}</p>
                                            </div>
                                        </div>

                                        <div className="text-right font-mono text-xs">
                                            <p className="font-bold text-slate-800 dark:text-slate-200">{ticker.price}</p>
                                            <p
                                                className={`text-[10px] font-semibold ${
                                                    ticker.isUp ? "text-emerald-500" : "text-rose-500"
                                                }`}
                                            >
                                                {ticker.change}
                                            </p>
                                        </div>
                                    </Link>
                                ))}
                            </div>
                        </div>

                        {/* 3. Top Contributors */}
                        <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 p-4 shadow-sm">
                            <div className="flex items-center justify-between mb-3">
                                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-white flex items-center gap-1.5">
                                    <Award size={15} className="text-amber-500" />
                                    <span>Top Nhà đầu tư nổi bật</span>
                                </h3>
                            </div>

                            <div className="space-y-3">
                                {TOP_CONTRIBUTORS.map((master) => (
                                    <div key={master.name} className="flex items-center justify-between text-xs">
                                        <div className="flex items-center gap-2 min-w-0">
                                            <UserAvatar name={master.name} size={32} />
                                            <div className="min-w-0">
                                                <p className="font-bold text-slate-900 dark:text-slate-100 truncate">
                                                    {master.name}
                                                </p>
                                                <p className="text-[10px] text-slate-500 dark:text-slate-400 font-medium">
                                                    {master.role}
                                                </p>
                                            </div>
                                        </div>

                                        <button
                                            type="button"
                                            onClick={() => toast.info(`Đã cập nhật theo dõi ${master.name}`)}
                                            className={`px-2.5 py-1 rounded-lg text-[11px] font-semibold transition-colors cursor-pointer shrink-0 ${
                                                master.isFollowed
                                                    ? "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400"
                                                    : "bg-blue-600 hover:bg-blue-500 text-white"
                                            }`}
                                        >
                                            {master.isFollowed ? "Đang theo dõi" : "+ Theo dõi"}
                                        </button>
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* 4. Community Guidelines */}
                        <div className="p-3.5 rounded-2xl bg-blue-50/70 dark:bg-blue-950/40 border border-blue-200/60 dark:border-blue-900/40 text-xs text-blue-900 dark:text-blue-200 space-y-1.5">
                            <div className="font-bold flex items-center gap-1.5 text-blue-700 dark:text-blue-300">
                                <ShieldCheck size={14} />
                                <span>Quy tắc cộng đồng văn minh</span>
                            </div>
                            <p className="text-[11px] text-blue-800/80 dark:text-blue-300/80 leading-relaxed">
                                Tôn trọng các ý kiến trái chiều, không lôi kéo đầu cơ ác ý và chia sẻ nhận định có cơ sở phân tích rõ ràng.
                            </p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

// Building Icon Helper Component
function BuildingIcon({ size = 16, className }: { size?: number; className?: string }) {
    return (
        <svg
            width={size}
            height={size}
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className={className}
        >
            <rect width="16" height="20" x="4" y="2" rx="2" ry="2" />
            <path d="M9 22v-4h6v4" />
            <path d="M8 6h.01" />
            <path d="M16 6h.01" />
            <path d="M12 6h.01" />
            <path d="M12 10h.01" />
            <path d="M12 14h.01" />
            <path d="M16 10h.01" />
            <path d="M16 14h.01" />
            <path d="M8 10h.01" />
            <path d="M8 14h.01" />
        </svg>
    );
}

// Ảnh đính kèm bài viết: ẩn hẳn khung nếu link ảnh hỏng thay vì để một ô trống.
function PostImage({ src }: { src: string }) {
    const [failed, setFailed] = useState(false);
    if (failed) return null;

    return (
        <div className="relative w-full aspect-[16/9] rounded-xl overflow-hidden mb-3.5 border border-slate-200 dark:border-slate-800">
            <Image
                src={src}
                alt="Chart"
                fill
                onError={() => setFailed(true)}
                className="object-cover hover:scale-102 transition-transform duration-300"
            />
        </div>
    );
}
