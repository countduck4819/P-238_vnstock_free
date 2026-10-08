"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Crown, Settings, Sparkles, UserRound } from "lucide-react";
import { useAuth } from "@/auth/AuthProvider";
import { Role } from "@/share/enum";
import UserAvatar from "@/share/components/UserAvatar";
import { AccountType } from "@/store/users/user.reducer";

const ACCOUNT_NAVIGATION = [
    { href: "/profile", label: "Hồ sơ cá nhân", icon: UserRound },
    { href: "/settings", label: "Cài đặt tài khoản", icon: Settings },
];

interface AccountPageShellProps {
    eyebrow: string;
    title: string;
    description: string;
    children: ReactNode;
}

export default function AccountPageShell({ eyebrow, title, description, children }: AccountPageShellProps) {
    const { user } = useAuth();
    const pathname = usePathname();

    if (!user) return null;

    const isPremium = user.accountType === AccountType.PREMIUM || user.role === Role.Admin;

    return (
        <section className="relative min-h-[calc(100vh-4.1rem)] overflow-hidden bg-gradient-to-b from-[#f7f7ff] via-white to-[#f4f1ff] px-4 py-8 transition-colors dark:from-slate-950 dark:via-slate-950 dark:to-indigo-950/30 sm:px-6 sm:py-10">
            <div className="pointer-events-none absolute -left-32 top-16 h-72 w-72 rounded-full bg-indigo-400/10 blur-3xl dark:bg-indigo-500/10" />
            <div className="pointer-events-none absolute -right-24 top-48 h-80 w-80 rounded-full bg-fuchsia-400/10 blur-3xl dark:bg-fuchsia-500/10" />

            <div className="relative mx-auto max-w-6xl">
                <div className="mb-7">
                    <div className="mb-2 inline-flex items-center gap-1.5 rounded-full border border-indigo-500/20 bg-indigo-500/10 px-3 py-1 text-xs font-bold text-indigo-600 dark:text-indigo-300">
                        <Sparkles size={13} /> {eyebrow}
                    </div>
                    <h1 className="bg-gradient-to-r from-slate-950 via-indigo-900 to-purple-800 bg-clip-text text-2xl font-black tracking-tight text-transparent dark:from-white dark:via-indigo-100 dark:to-purple-200 sm:text-3xl">
                        {title}
                    </h1>
                    <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500 dark:text-slate-400">{description}</p>
                </div>

                <div className="grid items-start gap-6 lg:grid-cols-[280px_minmax(0,1fr)]">
                    <aside className="overflow-hidden rounded-3xl border border-white/70 bg-white/90 shadow-xl shadow-indigo-950/5 backdrop-blur-xl dark:border-slate-800 dark:bg-slate-900/90 dark:shadow-black/20">
                        <div className="h-20 bg-gradient-to-r from-indigo-600 via-purple-600 to-pink-500" />
                        <div className="px-5 pb-5">
                            <div className="-mt-9 flex items-end justify-between">
                                <div className="rounded-full bg-white p-1.5 shadow-lg dark:bg-slate-900">
                                    <UserAvatar src={user.avatar} name={user.fullName || user.username} email={user.email} size={64} />
                                </div>
                                <span className={`mb-1 inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide ${isPremium ? "border-amber-400/30 bg-amber-400/10 text-amber-600 dark:text-amber-300" : "border-slate-200 bg-slate-100 text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"}`}>
                                    <Crown size={11} /> {isPremium ? "Cao cấp" : "Miễn phí"}
                                </span>
                            </div>
                            <h2 className="mt-3 truncate text-lg font-bold text-slate-900 dark:text-white">{user.fullName || user.username}</h2>
                            <p className="truncate text-xs text-slate-500 dark:text-slate-400">{user.email}</p>

                            <nav className="mt-5 space-y-1 border-t border-slate-100 pt-4 dark:border-slate-800">
                                {ACCOUNT_NAVIGATION.map((item) => {
                                    const Icon = item.icon;
                                    const active = pathname === item.href;
                                    return (
                                        <Link key={item.href} href={item.href} className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition-all ${active ? "bg-gradient-to-r from-indigo-600 to-purple-600 text-white shadow-md shadow-indigo-500/20" : "text-slate-600 hover:bg-slate-100 hover:text-indigo-600 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-indigo-300"}`}>
                                            <Icon size={17} /> {item.label}
                                        </Link>
                                    );
                                })}
                            </nav>

                            {!isPremium && (
                                <Link href="/nang-cap-hoi-vien" className="mt-4 block rounded-2xl border border-indigo-500/20 bg-gradient-to-br from-indigo-50 via-purple-50 to-pink-50 p-4 transition-all hover:-translate-y-0.5 hover:shadow-md dark:from-indigo-950/50 dark:via-purple-950/30 dark:to-slate-900">
                                    <div className="flex items-center gap-2 text-xs font-bold text-indigo-700 dark:text-indigo-300"><Crown size={15} /> Nâng cấp hội viên</div>
                                    <p className="mt-1 text-[11px] leading-4 text-slate-500 dark:text-slate-400">Mở khóa đầy đủ công cụ phân tích FinSight.</p>
                                </Link>
                            )}
                        </div>
                    </aside>

                    <main className="min-w-0">{children}</main>
                </div>
            </div>
        </section>
    );
}
