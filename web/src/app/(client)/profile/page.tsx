"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { LucideIcon } from "lucide-react";
import { AtSign, BadgeCheck, ChevronRight, Mail, MapPin, Settings, UserRound, UsersRound } from "lucide-react";
import { useAuth } from "@/auth/AuthProvider";
import { Role } from "@/share/enum";
import { AccountType, Gender } from "@/store/users/user.reducer";
import AccountPageShell from "../components/AccountPageShell";

const GENDER_LABELS: Partial<Record<Gender, string>> = {
    [Gender.MALE]: "Nam",
    [Gender.FEMALE]: "Nữ",
    [Gender.OTHER]: "Khác",
};

export default function ProfilePage() {
    const { user, loading } = useAuth();
    const router = useRouter();

    useEffect(() => {
        if (!loading && !user) router.replace("/login");
    }, [loading, user, router]);

    if (loading) return <div className="min-h-screen animate-pulse bg-slate-50 dark:bg-slate-950" />;
    if (!user) return null;

    const isPremium = user.accountType === AccountType.PREMIUM || user.role === Role.Admin;
    const roleLabel = user.role === Role.Admin ? "Quản trị viên" : "Người dùng";

    return (
        <AccountPageShell eyebrow="Không gian cá nhân" title="Hồ sơ cá nhân" description="Thông tin nhận diện và trạng thái tài khoản FinSight của bạn.">
            <div className="space-y-5">
                <div className="relative overflow-hidden rounded-3xl border border-slate-200/80 bg-white/90 p-6 shadow-lg shadow-slate-950/5 backdrop-blur-xl dark:border-slate-800 dark:bg-slate-900/90 sm:p-7">
                    <div className="pointer-events-none absolute -right-20 -top-24 h-56 w-56 rounded-full bg-gradient-to-br from-indigo-500/15 to-pink-500/15 blur-2xl" />
                    <div className="relative flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                        <div>
                            <div className="flex items-center gap-2">
                                <h2 className="text-xl font-bold text-slate-900 dark:text-white">Xin chào, {user.fullName || user.username}</h2>
                                <BadgeCheck className="text-indigo-500" size={20} />
                            </div>
                            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">Hồ sơ của bạn đã được đồng bộ với hệ thống FinSight.</p>
                        </div>
                        <div className="inline-flex w-fit items-center gap-2 rounded-2xl border border-indigo-500/20 bg-indigo-500/10 px-4 py-2.5 text-xs font-bold text-indigo-700 dark:text-indigo-300">
                            <BadgeCheck size={16} /> {isPremium ? "Hội viên Cao cấp" : "Hội viên Miễn phí"}
                        </div>
                    </div>
                </div>

                <div className="rounded-3xl border border-slate-200/80 bg-white/90 p-5 shadow-lg shadow-slate-950/5 backdrop-blur-xl dark:border-slate-800 dark:bg-slate-900/90 sm:p-7">
                    <div className="mb-5 flex items-center justify-between">
                        <div>
                            <h2 className="font-bold text-slate-900 dark:text-white">Thông tin tài khoản</h2>
                            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Thông tin đang được lưu trên hệ thống.</p>
                        </div>
                        <div className="rounded-xl bg-indigo-500/10 p-2.5 text-indigo-600 dark:text-indigo-300"><UserRound size={19} /></div>
                    </div>

                    <div className="grid gap-3 sm:grid-cols-2">
                        <Info icon={UserRound} label="Họ và tên" value={user.fullName || "Chưa cập nhật"} />
                        <Info icon={AtSign} label="Tên đăng nhập" value={user.username} />
                        <Info icon={Mail} label="Email" value={user.email} />
                        <Info icon={MapPin} label="Địa chỉ" value={user.address || "Chưa cập nhật"} />
                        <Info icon={UsersRound} label="Giới tính" value={user.gender ? GENDER_LABELS[user.gender] || "Khác" : "Chưa cập nhật"} />
                        <Info icon={BadgeCheck} label="Vai trò" value={roleLabel} />
                    </div>
                </div>

                <Link href="/settings" className="group flex items-center justify-between rounded-2xl border border-slate-200/80 bg-white/80 p-4 text-sm shadow-sm transition-all hover:border-indigo-500/30 hover:shadow-md dark:border-slate-800 dark:bg-slate-900/80">
                    <span className="flex items-center gap-3 font-semibold text-slate-700 dark:text-slate-200">
                        <span className="rounded-xl bg-purple-500/10 p-2 text-purple-600 dark:text-purple-300"><Settings size={17} /></span>
                        Đi tới cài đặt tài khoản
                    </span>
                    <ChevronRight className="text-slate-400 transition-transform group-hover:translate-x-1 group-hover:text-indigo-500" size={18} />
                </Link>
            </div>
        </AccountPageShell>
    );
}

function Info({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value: string }) {
    return (
        <div className="group rounded-2xl border border-slate-100 bg-slate-50/80 p-4 transition-colors hover:border-indigo-500/20 hover:bg-indigo-50/40 dark:border-slate-800 dark:bg-slate-800/50 dark:hover:border-indigo-500/30 dark:hover:bg-indigo-950/20">
            <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500"><Icon className="text-indigo-500" size={14} /> {label}</div>
            <p className="mt-2 break-words text-sm font-semibold text-slate-800 dark:text-slate-100">{value}</p>
        </div>
    );
}
