"use client";

import { Fragment, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, Check, CheckCheck, Loader2, MessageCircle, Search, Send, Wifi, WifiOff } from "lucide-react";
import { toast } from "react-toastify";
import { useAuth } from "@/auth/AuthProvider";
import { useAppDispatch, useAppSelector } from "@/redux/hooks";
import UserAvatar from "@/share/components/UserAvatar";
import {
    fetchMessages,
    openConversation,
    searchMembers,
} from "@/store/community-chat/community-chat.api";
import { ChatMember, ChatMessage, Conversation } from "@/store/community-chat/community-chat.reducer";
import { useCommunityRealtime } from "../components/CommunityRealtimeProvider";
import { formatRelativeTime } from "../components/formatRelativeTime";

const TYPING_IDLE_MS = 2500;
const QUICK_GREETINGS = ["Chào bạn 👋", "Bạn đang theo dõi mã nào?", "Cho mình hỏi về nhận định của bạn"];

export default function MessagesPage() {
    return (
        <Suspense fallback={<CenteredSpinner />}>
            <Messenger />
        </Suspense>
    );
}

function Messenger() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const dispatch = useAppDispatch();
    const { user, loading: authLoading } = useAuth();
    const { connected } = useCommunityRealtime();
    const { conversations, onlineUserIds } = useAppSelector((state) => state.communityChat);

    const activeId = Number(searchParams.get("c")) || null;
    const recipientParam = Number(searchParams.get("userId")) || null;
    const active = conversations.find((c) => c.id === activeId) ?? null;

    const selectConversation = useCallback(
        (conversationId: number) => router.replace(`/cong-dong/tin-nhan?c=${conversationId}`),
        [router]
    );

    // `?userId=` comes from "Nhắn tin" buttons on the feed: open (or create)
    // the conversation with that member, then switch to `?c=`.
    useEffect(() => {
        if (!recipientParam || !user?.id) return;
        dispatch(openConversation(recipientParam))
            .unwrap()
            .then((conversation) => selectConversation(conversation.id))
            .catch((err) => toast.error(typeof err === "string" ? err : "Không thể mở hội thoại"));
    }, [dispatch, recipientParam, user?.id, selectConversation]);

    if (authLoading && !user) return <CenteredSpinner />;

    if (!user) {
        return (
            <div className="min-h-[70vh] flex flex-col items-center justify-center gap-3 text-center px-4">
                <MessageCircle size={40} className="text-blue-500" />
                <p className="font-semibold">Đăng nhập để nhắn tin với các nhà đầu tư khác</p>
                <Link
                    href="/login"
                    className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold"
                >
                    Đăng nhập
                </Link>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100">
            <div className="max-w-[1200px] mx-auto px-0 sm:px-4 py-0 sm:py-4">
                <div className={`${active ? "hidden md:flex" : "flex"} items-center justify-between px-4 sm:px-0 py-3 sm:pt-0`}>
                    <Link
                        href="/cong-dong"
                        className="inline-flex items-center gap-1.5 text-sm font-semibold text-slate-600 dark:text-slate-300 hover:text-blue-600"
                    >
                        <ArrowLeft size={16} /> Cộng đồng
                    </Link>
                    <ConnectionBadge connected={connected} />
                </div>

                <div className={`grid grid-cols-1 md:grid-cols-[320px_1fr] ${active ? "h-[calc(100dvh-4.1rem-1px)]" : "h-[calc(100dvh-7.2rem)]"} sm:h-[calc(100dvh-8.5rem)] sm:rounded-2xl overflow-hidden border-y sm:border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm`}>
                    <aside className={`${active ? "hidden md:flex" : "flex"} flex-col border-r border-slate-200/80 dark:border-slate-800 min-h-0`}>
                        <ConversationSidebar
                            conversations={conversations}
                            onlineUserIds={onlineUserIds}
                            activeId={activeId}
                            viewerId={user.id}
                            onSelect={selectConversation}
                            onPickMember={(memberId) => router.replace(`/cong-dong/tin-nhan?userId=${memberId}`)}
                        />
                    </aside>

                    <section className={`${active ? "flex" : "hidden md:flex"} flex-col min-h-0`}>
                        {active ? (
                            <ConversationThread
                                key={active.id}
                                conversation={active}
                                viewerId={user.id}
                                online={onlineUserIds.includes(active.partner.id)}
                                onBack={() => router.replace("/cong-dong/tin-nhan")}
                            />
                        ) : (
                            <div className="flex-1 flex flex-col items-center justify-center text-center text-slate-400 gap-2 p-6">
                                <MessageCircle size={40} className="text-slate-300 dark:text-slate-700" />
                                <p className="text-sm font-semibold">Chọn một hội thoại hoặc tìm thành viên để bắt đầu nhắn tin</p>
                            </div>
                        )}
                    </section>
                </div>
            </div>
        </div>
    );
}

function ConversationSidebar({
    conversations,
    onlineUserIds,
    activeId,
    viewerId,
    onSelect,
    onPickMember,
}: {
    conversations: Conversation[];
    onlineUserIds: number[];
    activeId: number | null;
    viewerId: number;
    onSelect: (conversationId: number) => void;
    onPickMember: (memberId: number) => void;
}) {
    const { conversationsLoaded } = useAppSelector((state) => state.communityChat);
    const [keyword, setKeyword] = useState("");
    const [members, setMembers] = useState<ChatMember[]>([]);
    const [searching, setSearching] = useState(false);
    const term = keyword.trim();

    useEffect(() => {
        if (!term) {
            setMembers([]);
            return;
        }
        let cancelled = false;
        setSearching(true);
        const timer = setTimeout(() => {
            searchMembers(term)
                .then((result) => !cancelled && setMembers(result))
                .catch(() => !cancelled && setMembers([]))
                .finally(() => !cancelled && setSearching(false));
        }, 300);
        return () => {
            cancelled = true;
            clearTimeout(timer);
        };
    }, [term]);

    return (
        <>
            <div className="p-3 border-b border-slate-200/80 dark:border-slate-800">
                <h2 className="text-sm font-bold mb-2">Tin nhắn</h2>
                <div className="relative">
                    <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                    <input
                        value={keyword}
                        onChange={(e) => setKeyword(e.target.value)}
                        placeholder="Tìm thành viên để nhắn tin..."
                        className="w-full pl-8 pr-3 py-2 rounded-xl bg-slate-100 dark:bg-slate-800 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500/50"
                    />
                </div>
            </div>

            <div className="flex-1 overflow-y-auto">
                {term ? (
                    searching ? (
                        <CenteredSpinner small />
                    ) : members.length === 0 ? (
                        <EmptyNote>Không tìm thấy thành viên phù hợp</EmptyNote>
                    ) : (
                        members.map((member) => (
                            <button
                                key={member.id}
                                type="button"
                                onClick={() => {
                                    setKeyword("");
                                    onPickMember(member.id);
                                }}
                                className="w-full flex items-center gap-3 px-3 py-2.5 hover:bg-slate-50 dark:hover:bg-slate-800/60 text-left cursor-pointer"
                            >
                                <AvatarWithPresence member={member} online={onlineUserIds.includes(member.id)} />
                                <div className="min-w-0">
                                    <p className="text-sm font-semibold truncate">{member.name}</p>
                                    <p className="text-[11px] text-slate-400 truncate">{member.role}</p>
                                </div>
                            </button>
                        ))
                    )
                ) : !conversationsLoaded ? (
                    <CenteredSpinner small />
                ) : conversations.length === 0 ? (
                    <EmptyNote>Chưa có hội thoại nào. Tìm một thành viên hoặc bấm “Nhắn tin” trên bài viết để bắt đầu.</EmptyNote>
                ) : (
                    conversations.map((conversation) => {
                        const isActive = conversation.id === activeId;
                        const fromMe = conversation.lastSenderId === viewerId;
                        return (
                            <button
                                key={conversation.id}
                                type="button"
                                onClick={() => onSelect(conversation.id)}
                                className={`w-full flex items-center gap-3 px-3 py-2.5 text-left cursor-pointer transition-colors ${
                                    isActive
                                        ? "bg-blue-50 dark:bg-blue-950/50"
                                        : "hover:bg-slate-50 dark:hover:bg-slate-800/60"
                                }`}
                            >
                                <AvatarWithPresence
                                    member={conversation.partner}
                                    online={onlineUserIds.includes(conversation.partner.id)}
                                />
                                <div className="min-w-0 flex-1">
                                    <div className="flex items-center justify-between gap-2">
                                        <p className="text-sm font-semibold truncate">{conversation.partner.name}</p>
                                        {conversation.lastMessageAt && (
                                            <span className="text-[10px] text-slate-400 shrink-0">
                                                {formatRelativeTime(conversation.lastMessageAt)}
                                            </span>
                                        )}
                                    </div>
                                    <div className="flex items-center justify-between gap-2">
                                        <p
                                            className={`text-xs truncate ${
                                                conversation.unreadCount > 0
                                                    ? "font-bold text-slate-900 dark:text-white"
                                                    : "text-slate-500 dark:text-slate-400"
                                            }`}
                                        >
                                            {conversation.lastMessagePreview
                                                ? `${fromMe ? "Bạn: " : ""}${conversation.lastMessagePreview}`
                                                : "Bắt đầu cuộc trò chuyện"}
                                        </p>
                                        {conversation.unreadCount > 0 && (
                                            <span className="min-w-5 h-5 px-1.5 rounded-full bg-rose-500 text-white text-[10px] font-bold flex items-center justify-center shrink-0">
                                                {conversation.unreadCount}
                                            </span>
                                        )}
                                    </div>
                                </div>
                            </button>
                        );
                    })
                )}
            </div>
        </>
    );
}

function ConversationThread({
    conversation,
    viewerId,
    online,
    onBack,
}: {
    conversation: Conversation;
    viewerId: number;
    online: boolean;
    onBack: () => void;
}) {
    const dispatch = useAppDispatch();
    const { sendMessage, markRead, setTyping } = useCommunityRealtime();
    const thread = useAppSelector((state) => state.communityChat.threads[conversation.id]);
    const partnerTyping = useAppSelector((state) => state.communityChat.typing[conversation.id]);
    const [draft, setDraft] = useState("");
    const [sending, setSending] = useState(false);
    const scrollRef = useRef<HTMLDivElement>(null);
    const typingTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
    const messages = useMemo(() => thread?.items ?? [], [thread?.items]);

    useEffect(() => {
        if (!thread?.loaded) dispatch(fetchMessages({ conversationId: conversation.id }));
    }, [dispatch, conversation.id, thread?.loaded]);

    // Opening the conversation, or receiving while it is open, marks it read.
    useEffect(() => {
        if (conversation.unreadCount > 0) markRead(conversation.id);
    }, [conversation.id, conversation.unreadCount, markRead]);

    const lastMessageId = messages[messages.length - 1]?.id;
    useEffect(() => {
        scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
    }, [lastMessageId, partnerTyping]);

    useEffect(
        () => () => {
            if (typingTimer.current) clearTimeout(typingTimer.current);
        },
        []
    );

    const handleDraftChange = (value: string) => {
        setDraft(value);
        if (!typingTimer.current) setTyping(conversation.id, true);
        else clearTimeout(typingTimer.current);
        typingTimer.current = setTimeout(() => {
            setTyping(conversation.id, false);
            typingTimer.current = null;
        }, TYPING_IDLE_MS);
    };

    const handleSend = async () => {
        const content = draft.trim();
        if (!content || sending) return;
        setSending(true);
        try {
            await sendMessage(conversation.id, content);
            setDraft("");
            if (typingTimer.current) {
                clearTimeout(typingTimer.current);
                typingTimer.current = null;
                setTyping(conversation.id, false);
            }
        } catch (err) {
            toast.error(err instanceof Error ? err.message : typeof err === "string" ? err : "Không thể gửi tin nhắn");
        } finally {
            setSending(false);
        }
    };

    const loadOlder = () => {
        if (!thread || thread.loading || !thread.hasMore) return;
        dispatch(fetchMessages({ conversationId: conversation.id, beforeId: messages[0]?.id }));
    };

    // The read receipt sits under the latest message I sent that was read.
    const lastSeenId = [...messages].reverse().find((m) => m.senderId === viewerId && m.readAt)?.id;

    return (
        <>
            <header className="flex items-center gap-3 px-4 py-3 border-b border-slate-200/80 dark:border-slate-800">
                <button type="button" onClick={onBack} className="md:hidden p-1 -ml-1 cursor-pointer" aria-label="Quay lại">
                    <ArrowLeft size={18} />
                </button>
                <AvatarWithPresence member={conversation.partner} online={online} />
                <div className="min-w-0">
                    <p className="text-sm font-bold truncate">{conversation.partner.name}</p>
                    <p className="text-[11px] text-slate-400">
                        {partnerTyping ? "Đang soạn tin..." : online ? "Đang hoạt động" : conversation.partner.badge}
                    </p>
                </div>
            </header>

            <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-0.5 bg-slate-50/60 dark:bg-slate-950/40">
                {thread?.hasMore && (
                    <div className="text-center pb-2">
                        <button
                            type="button"
                            onClick={loadOlder}
                            disabled={thread.loading}
                            className="text-xs font-semibold text-blue-600 hover:underline cursor-pointer disabled:opacity-50"
                        >
                            {thread.loading ? "Đang tải..." : "Xem tin nhắn cũ hơn"}
                        </button>
                    </div>
                )}

                {!thread?.loaded ? (
                    <CenteredSpinner small />
                ) : messages.length === 0 ? (
                    <div className="flex flex-col items-center text-center gap-2 py-10">
                        <UserAvatar src={conversation.partner.avatar} name={conversation.partner.name} size={64} />
                        <p className="text-sm font-bold">{conversation.partner.name}</p>
                        <p className="text-xs text-slate-400">{conversation.partner.badge}</p>
                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-2">Hãy gửi lời chào đầu tiên 👋</p>
                        <div className="flex flex-wrap justify-center gap-2 mt-1">
                            {QUICK_GREETINGS.map((text) => (
                                <button
                                    key={text}
                                    type="button"
                                    onClick={() => setDraft(text)}
                                    className="px-3 py-1.5 rounded-full border border-blue-200 dark:border-blue-900 text-xs font-semibold text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-950/50 cursor-pointer"
                                >
                                    {text}
                                </button>
                            ))}
                        </div>
                    </div>
                ) : (
                    messages.map((message, i) => {
                        const prev = messages[i - 1];
                        const next = messages[i + 1];
                        const day = dayKey(message.createdAt);
                        const newDay = !prev || dayKey(prev.createdAt) !== day;
                        const lastInGroup =
                            !next || next.senderId !== message.senderId || dayKey(next.createdAt) !== day;
                        return (
                            <Fragment key={message.id}>
                                {newDay && <DaySeparator date={message.createdAt} />}
                                <MessageBubble
                                    message={message}
                                    mine={message.senderId === viewerId}
                                    seen={message.id === lastSeenId}
                                    partner={conversation.partner}
                                    lastInGroup={lastInGroup}
                                />
                            </Fragment>
                        );
                    })
                )}

                {partnerTyping && (
                    <div className="flex">
                        <span className="px-3 py-2 rounded-2xl bg-white dark:bg-slate-800 text-xs text-slate-400 animate-pulse">
                            {conversation.partner.name} đang soạn tin...
                        </span>
                    </div>
                )}
            </div>

            <form
                onSubmit={(e) => {
                    e.preventDefault();
                    handleSend();
                }}
                className="flex items-end gap-2 p-3 border-t border-slate-200/80 dark:border-slate-800"
            >
                <textarea
                    rows={1}
                    value={draft}
                    maxLength={2000}
                    onChange={(e) => handleDraftChange(e.target.value)}
                    onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                            e.preventDefault();
                            handleSend();
                        }
                    }}
                    placeholder="Nhập tin nhắn..."
                    title="Enter để gửi, Shift+Enter để xuống dòng"
                    className="flex-1 resize-none max-h-32 bg-slate-100 dark:bg-slate-800 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/50"
                />
                <button
                    type="submit"
                    disabled={!draft.trim() || sending}
                    className="p-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white cursor-pointer"
                    aria-label="Gửi"
                >
                    {sending ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
                </button>
            </form>
        </>
    );
}

function dayKey(value: string) {
    return new Date(value).toDateString();
}

function DaySeparator({ date }: { date: string }) {
    const d = new Date(date);
    const today = new Date();
    const yesterday = new Date();
    yesterday.setDate(today.getDate() - 1);
    const label =
        d.toDateString() === today.toDateString()
            ? "Hôm nay"
            : d.toDateString() === yesterday.toDateString()
              ? "Hôm qua"
              : d.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" });
    return (
        <div className="flex items-center gap-3 py-2">
            <span className="flex-1 h-px bg-slate-200 dark:bg-slate-800" />
            <span className="text-[11px] font-semibold text-slate-400">{label}</span>
            <span className="flex-1 h-px bg-slate-200 dark:bg-slate-800" />
        </div>
    );
}

// Tin liên tiếp của cùng một người gom thành một cụm: avatar và giờ chỉ hiện ở tin cuối cụm.
function MessageBubble({
    message,
    mine,
    seen,
    partner,
    lastInGroup,
}: {
    message: ChatMessage;
    mine: boolean;
    seen: boolean;
    partner: ChatMember;
    lastInGroup: boolean;
}) {
    const time = new Date(message.createdAt).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
    return (
        <div className={`flex items-end gap-2 ${mine ? "justify-end" : "justify-start"} ${lastInGroup ? "pb-1.5" : ""}`}>
            {!mine && (
                <div className="w-7 shrink-0 self-end mb-4">
                    {lastInGroup && <UserAvatar src={partner.avatar} name={partner.name} size={28} />}
                </div>
            )}
            <div className={`flex flex-col max-w-[75%] min-w-0 ${mine ? "items-end" : "items-start"}`}>
                <div
                    className={`px-3.5 py-2 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap wrap-anywhere ${
                        mine
                            ? `bg-blue-600 text-white ${lastInGroup ? "rounded-br-md" : ""}`
                            : `bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-100 border border-slate-200/70 dark:border-slate-700/60 ${lastInGroup ? "rounded-bl-md" : ""}`
                    }`}
                    title={new Date(message.createdAt).toLocaleString("vi-VN")}
                >
                    {message.content}
                </div>
                {lastInGroup && (
                    <span className="flex items-center gap-1 text-[10px] text-slate-400 mt-0.5 px-1">
                        {time}
                        {mine && (seen ? <CheckCheck size={12} className="text-blue-500" /> : <Check size={12} />)}
                        {seen && <span>Đã xem</span>}
                    </span>
                )}
            </div>
        </div>
    );
}

function AvatarWithPresence({ member, online }: { member: ChatMember; online: boolean }) {
    return (
        <div className="relative shrink-0">
            <UserAvatar src={member.avatar} name={member.name} size={38} />
            {online && (
                <span className="absolute bottom-0 right-0 w-2.5 h-2.5 rounded-full bg-emerald-500 ring-2 ring-white dark:ring-slate-900" />
            )}
        </div>
    );
}

function ConnectionBadge({ connected }: { connected: boolean }) {
    return connected ? (
        <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-600">
            <Wifi size={13} /> Trực tuyến
        </span>
    ) : (
        <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-amber-600">
            <WifiOff size={13} /> Đang kết nối lại...
        </span>
    );
}

function EmptyNote({ children }: { children: React.ReactNode }) {
    return <p className="text-xs text-slate-400 text-center px-6 py-8">{children}</p>;
}

function CenteredSpinner({ small = false }: { small?: boolean }) {
    return (
        <div className={`flex items-center justify-center ${small ? "py-8" : "min-h-[60vh]"}`}>
            <Loader2 size={small ? 20 : 28} className="animate-spin text-blue-600" />
        </div>
    );
}
