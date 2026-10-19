"use client";

import Link from "next/link";
import { MessageCircle } from "lucide-react";
import { useAppSelector } from "@/redux/hooks";
import { selectUnreadTotal } from "@/store/community-chat/community-chat.reducer";

/** Header shortcut to the inbox with the live unread badge. */
export default function MessagesButton() {
    const unread = useAppSelector(selectUnreadTotal);
    return (
        <Link
            href="/cong-dong/tin-nhan"
            className="relative inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-white/10 hover:bg-white/20 text-white font-semibold text-xs sm:text-sm transition-all shrink-0"
        >
            <MessageCircle size={16} />
            <span>Tin nhắn</span>
            {unread > 0 && (
                <span className="absolute -top-1.5 -right-1.5 min-w-5 h-5 px-1.5 rounded-full bg-rose-500 text-white text-[10px] font-bold flex items-center justify-center">
                    {unread > 99 ? "99+" : unread}
                </span>
            )}
        </Link>
    );
}
