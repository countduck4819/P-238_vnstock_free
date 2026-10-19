"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { LucideIcon } from "lucide-react";
import { Bell, ChevronRight, LockKeyhole, Mail, MoonStar, ShieldCheck, Smartphone, UserRound } from "lucide-react";
import { useAuth } from "@/auth/AuthProvider";
import AccountPageShell from "../components/AccountPageShell";

export default function SettingsPage() {
    const { user, loading } = useAuth();
    const router = useRouter();
    const [emailNews, setEmailNews] = useState(true);
    const [marketAlerts, setMarketAlerts] = useState(true);

    useEffect(() => {
        if (!loading && !user) router.replace("/login");
    }, [loading, user, router]);

    if (loading) return <div className="min-h-screen animate-pulse bg-slate-50 dark:bg-slate-950" />;
    if (!user) return null;

    return (
        <AccountPageShell eyebrow="Tùy chỉnh trải nghiệm" title="Cài đặt tài khoản" description="Quản lý thông báo, giao diện và các tùy chọn bảo mật cho tài khoản của bạn.">
            <div className="space-y-5">
                <SettingsCard icon={UserRound} title="Tài khoản" description="Thông tin đăng nhập và hồ sơ cá nhân">
                    <Link href="/profile" className="group flex items-center justify-between rounded-2xl bg-slate-50 p-4 transition-colors hover:bg-indigo-50/70 dark:bg-slate-800/50 dark:hover:bg-indigo-950/30">
                        <div className="min-w-0">
                            <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">{user.fullName || user.username}</p>
                            <p className="truncate text-xs text-slate-500 dark:text-slate-400">{user.email}</p>
                        </div>
                        <ChevronRight className="ml-3 shrink-0 text-slate-400 transition-transform group-hover:translate-x-1 group-hover:text-indigo-500" size={18} />
                    </Link>
                </SettingsCard>

                <SettingsCard icon={Bell} title="Thông báo" description="Chọn những cập nhật bạn muốn nhận">
                    <div className="divide-y divide-slate-100 dark:divide-slate-800">
                        <ToggleRow icon={Mail} title="Bản tin qua email" description="Nhận tổng hợp thị trường và tin tức nổi bật." checked={emailNews} onChange={setEmailNews} />
                        <ToggleRow icon={Smartphone} title="Cảnh báo thị trường" description="Nhận thông báo khi có biến động quan trọng." checked={marketAlerts} onChange={setMarketAlerts} />
                    </div>
                </SettingsCard>

                <SettingsCard icon={MoonStar} title="Giao diện" description="Hiển thị phù hợp với môi trường làm việc">
                    <div className="flex items-center justify-between rounded-2xl bg-slate-50 p-4 dark:bg-slate-800/50">
                        <div>
                            <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">Chế độ sáng / tối</p>
                            <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">Sử dụng nút chuyển giao diện trên thanh điều hướng.</p>
                        </div>
                        <span className="ml-3 rounded-full border border-indigo-500/20 bg-indigo-500/10 px-3 py-1 text-[10px] font-bold whitespace-nowrap shrink-0 text-indigo-600 dark:text-indigo-300">TỰ ĐỘNG LƯU</span>
                    </div>
                </SettingsCard>

                <SettingsCard icon={LockKeyhole} title="Bảo mật" description="Bảo vệ tài khoản FinSight của bạn">
                    <div className="flex items-center gap-3 rounded-2xl border border-emerald-500/20 bg-emerald-500/5 p-4">
                        <div className="rounded-xl bg-emerald-500/10 p-2.5 text-emerald-600 dark:text-emerald-400"><ShieldCheck size={19} /></div>
                        <div>
                            <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">Tài khoản đang được bảo vệ</p>
                            <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">Phiên đăng nhập hiện tại đã được xác thực.</p>
                        </div>
                    </div>
                </SettingsCard>
            </div>
        </AccountPageShell>
    );
}

function SettingsCard({ icon: Icon, title, description, children }: { icon: LucideIcon; title: string; description: string; children: ReactNode }) {
    return (
        <section className="rounded-3xl border border-slate-200/80 bg-white/90 p-5 shadow-lg shadow-slate-950/5 backdrop-blur-xl dark:border-slate-800 dark:bg-slate-900/90 sm:p-6">
            <div className="mb-5 flex items-start gap-3">
                <div className="rounded-2xl bg-gradient-to-br from-indigo-500/15 to-purple-500/15 p-3 text-indigo-600 dark:text-indigo-300"><Icon size={20} /></div>
                <div><h2 className="font-bold text-slate-900 dark:text-white">{title}</h2><p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{description}</p></div>
            </div>
            {children}
        </section>
    );
}

function ToggleRow({ icon: Icon, title, description, checked, onChange }: { icon: LucideIcon; title: string; description: string; checked: boolean; onChange: (value: boolean) => void }) {
    return (
        <div className="flex items-center justify-between gap-4 py-4 first:pt-0 last:pb-0">
            <div className="flex min-w-0 items-center gap-3">
                <div className="shrink-0 rounded-xl bg-slate-100 p-2.5 text-slate-500 dark:bg-slate-800 dark:text-slate-300"><Icon size={17} /></div>
                <div><p className="text-sm font-semibold text-slate-800 dark:text-slate-100">{title}</p><p className="mt-0.5 text-xs leading-5 text-slate-500 dark:text-slate-400">{description}</p></div>
            </div>
            <button type="button" role="switch" aria-checked={checked} aria-label={title} onClick={() => onChange(!checked)} className={`relative h-6 w-11 shrink-0 cursor-pointer rounded-full transition-colors ${checked ? "bg-gradient-to-r from-indigo-600 to-purple-600" : "bg-slate-300 dark:bg-slate-700"}`}>
                <span className={`absolute left-1 top-1 h-4 w-4 rounded-full bg-white shadow-sm transition-transform ${checked ? "translate-x-5" : "translate-x-0"}`} />
            </button>
        </div>
    );
}
