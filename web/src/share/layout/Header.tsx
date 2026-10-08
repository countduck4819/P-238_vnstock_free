"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import Image from "next/image";
import {
    LogOut,
    User,
    Settings,
    Crown,
    ShieldCheck,
    Menu,
    X,
    Home,
    Users,
    TrendingUp,
    Info,
    Globe,
    LayoutDashboard,
} from "lucide-react";
import { useAuth } from "@/auth/AuthProvider";
import SearchBox from "../components/SearchBox";
import ThemeToggle from "@/components/theme/ThemeToggle";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { Role } from "../enum";
import { AccountType } from "@/store/users/user.reducer";
import UserAvatar from "@/share/components/UserAvatar";
import BrandLogo from "../components/BrandLogo";

const NAV_ITEMS = [
    { label: "Giới thiệu FinSight", href: "/", icon: Globe, exact: true },
    { label: "Trang chủ", href: "/home", icon: Home, exact: false },
    { label: "Bản đồ nhiệt", href: "/dashboard", icon: LayoutDashboard, exact: false },
    { label: "Thị trường", href: "/ma-chung-khoan/vnindex", icon: TrendingUp, matchPrefix: "/ma-chung-khoan" },
    { label: "Cộng đồng", href: "/cong-dong", icon: Users, matchPrefix: "/cong-dong" },
];

export default function Header() {
    const { user, logout } = useAuth();
    const pathname = usePathname();
    const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

    const isLinkActive = (item: (typeof NAV_ITEMS)[0]) => {
        if (!pathname) return false;
        if (item.exact) {
            return pathname === item.href;
        }
        if (item.matchPrefix) {
            return pathname.startsWith(item.matchPrefix);
        }
        return pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
    };

    return (
        <header
            className="
        fixed top-0 left-0 w-full z-50
        backdrop-blur-md bg-white/90 dark:bg-slate-950/90 border-b border-slate-200/80 dark:border-slate-800/80 transition-colors duration-200
      "
        >
            <div className="max-w-[95vw] 2xl:max-w-[1600px] mx-auto h-[4.1rem] sm:h-[4.5rem] flex items-center justify-between px-3 sm:px-6">
                {/* LEFT: Logo & Desktop Nav */}
                <div className="flex items-center gap-6 lg:gap-8 xl:gap-9">
                    <Link href="/home" className="flex items-center shrink-0 pr-2">
                        <BrandLogo size="md" />
                    </Link>

                    {/* Desktop Navigation Links */}
                    <nav className="hidden lg:flex items-center gap-1.5 xl:gap-2 text-[14.5px] sm:text-[15px]">
                        {NAV_ITEMS.map((item) => {
                            const isActive = isLinkActive(item);
                            return (
                                <Link
                                    key={item.href}
                                    href={item.href}
                                    className={`relative px-3.5 py-1.5 rounded-xl transition-all duration-200 whitespace-nowrap flex items-center gap-2 ${
                                        isActive
                                            ? "text-indigo-600 dark:text-white font-bold bg-indigo-500/10 dark:bg-indigo-500/20 shadow-xs border border-indigo-500/25 dark:border-indigo-500/35"
                                            : "hover:text-indigo-600 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800/80 text-slate-600 dark:text-slate-300 font-medium"
                                    }`}
                                >
                                    <span>{item.label}</span>
                                    {isActive && (
                                        <span className="w-1.5 h-1.5 rounded-full bg-gradient-to-r from-indigo-500 to-pink-500 animate-pulse shrink-0" />
                                    )}
                                </Link>
                            );
                        })}
                    </nav>
                </div>

                {/* RIGHT: Search + Theme + Notifications + User Profile */}
                <div className="flex items-center gap-1.5 sm:gap-3">
                    {/* SearchBox (Desktop & Tablet) */}
                    <div className="hidden md:block">
                        <SearchBox />
                    </div>

                    <ThemeToggle />

                    {user ? (
                        <DropdownMenu.Root>
                            <DropdownMenu.Trigger asChild>
                                <button
                                    type="button"
                                    className="rounded-full cursor-pointer focus:outline-none hover:ring-2 hover:ring-indigo-500/50 transition-all shrink-0"
                                >
                                    <UserAvatar
                                        src={user?.avatar}
                                        name={user?.fullName || user?.username}
                                        email={user?.email}
                                        size={32}
                                    />
                                </button>
                            </DropdownMenu.Trigger>

                            <DropdownMenu.Content
                                className="mt-2 w-56 bg-white dark:bg-slate-900 rounded-2xl shadow-xl border border-slate-200 dark:border-slate-800 p-3 text-sm z-[999] text-slate-800 dark:text-slate-200"
                                align="end"
                            >
                                <div className="flex flex-col items-center pb-3 border-b border-slate-100 dark:border-slate-800">
                                    <UserAvatar
                                        src={user?.avatar}
                                        name={user?.fullName || user?.username}
                                        email={user?.email}
                                        size={44}
                                        className="mb-1.5"
                                    />
                                    <p className="font-semibold text-slate-900 dark:text-white truncate max-w-[12rem]">
                                        {user?.fullName || user?.username || "User"}
                                    </p>
                                    <p
                                        className={`text-[11px] font-semibold mt-0.5 ${
                                            user?.accountType ===
                                                AccountType.PREMIUM ||
                                            user?.role === Role.Admin
                                                ? "bg-gradient-to-r from-indigo-500 to-pink-500 bg-clip-text text-transparent"
                                                : "text-slate-500 dark:text-slate-400"
                                        }`}
                                    >
                                        {user?.accountType ===
                                            AccountType.PREMIUM ||
                                        user?.role === Role.Admin
                                            ? "Hội viên Cao cấp"
                                            : "Hội viên Miễn phí"}
                                    </p>
                                </div>

                                <div className="mt-2 flex flex-col space-y-1 text-xs">
                                    <DropdownMenu.Item asChild>
                                        {user?.role === Role?.Admin ? (
                                            <Link
                                                href="/admin"
                                                className="flex items-center gap-2 px-2.5 py-2 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 cursor-pointer"
                                            >
                                                <ShieldCheck size={15} /> Admin Dashboard
                                            </Link>
                                        ) : user?.role === Role?.User &&
                                          user?.accountType ===
                                              AccountType?.FREE ? (
                                            <Link
                                                href="/nang-cap-hoi-vien"
                                                className="flex items-center gap-2 px-2.5 py-2 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 text-indigo-600 dark:text-indigo-400 font-semibold cursor-pointer"
                                            >
                                                <Crown size={15} /> Nâng cấp Hội viên
                                            </Link>
                                        ) : null}
                                    </DropdownMenu.Item>

                                    <DropdownMenu.Item asChild>
                                        <Link
                                            href="/profile"
                                            className="flex items-center gap-2 px-2.5 py-2 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 cursor-pointer"
                                        >
                                            <User size={15} /> Hồ sơ cá nhân
                                        </Link>
                                    </DropdownMenu.Item>

                                    <DropdownMenu.Item asChild>
                                        <Link
                                            href="/settings"
                                            className="flex items-center gap-2 px-2.5 py-2 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 cursor-pointer"
                                        >
                                            <Settings size={15} /> Cài đặt tài khoản
                                        </Link>
                                    </DropdownMenu.Item>

                                    <DropdownMenu.Item
                                        onSelect={logout}
                                        asChild
                                    >
                                        <button
                                            type="button"
                                            className="cursor-pointer flex items-center gap-2 px-2.5 py-2 rounded-xl text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950/40 w-full text-left"
                                        >
                                            <LogOut size={15} /> Đăng xuất
                                        </button>
                                    </DropdownMenu.Item>
                                </div>
                            </DropdownMenu.Content>
                        </DropdownMenu.Root>
                    ) : (
                        <Link
                            href="/login"
                            className="px-3.5 py-1.5 text-xs font-semibold text-white bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 rounded-xl shadow-sm transition-all"
                        >
                            Đăng nhập
                        </Link>
                    )}

                    {/* Mobile Hamburger Button */}
                    <button
                        onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                        className="lg:hidden p-2 rounded-xl text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer"
                        aria-label="Toggle navigation menu"
                    >
                        {mobileMenuOpen ? <X size={20} /> : <Menu size={20} />}
                    </button>
                </div>
            </div>

            {/* Mobile Navigation Drawer / Dropdown */}
            {mobileMenuOpen && (
                <div className="lg:hidden border-t border-slate-200/80 dark:border-slate-800 bg-white/95 dark:bg-slate-950/95 backdrop-blur-xl px-4 py-4 space-y-4 shadow-xl">
                    {/* Mobile Search */}
                    <div className="w-full">
                        <SearchBox />
                    </div>

                    {/* Mobile Nav Links */}
                    <nav className="flex flex-col space-y-1 text-sm">
                        {NAV_ITEMS.map((item) => {
                            const isActive = isLinkActive(item);
                            const Icon = item.icon;
                            return (
                                <Link
                                    key={item.href}
                                    href={item.href}
                                    onClick={() => setMobileMenuOpen(false)}
                                    className={`flex items-center justify-between px-3 py-2.5 rounded-xl transition-colors ${
                                        isActive
                                            ? "bg-indigo-500/10 dark:bg-indigo-500/20 text-indigo-600 dark:text-white font-bold border border-indigo-500/25 dark:border-indigo-500/35"
                                            : "text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800/80 hover:text-indigo-600 font-medium"
                                    }`}
                                >
                                    <div className="flex items-center gap-3">
                                        <Icon
                                            size={18}
                                            className={
                                                isActive
                                                    ? "text-indigo-600 dark:text-indigo-400"
                                                    : "text-indigo-500"
                                            }
                                        />
                                        <span>{item.label}</span>
                                    </div>
                                    {isActive && (
                                        <span className="w-1.5 h-1.5 rounded-full bg-gradient-to-r from-indigo-500 to-pink-500 animate-pulse" />
                                    )}
                                </Link>
                            );
                        })}
                    </nav>

                    {/* Member upgrade link on mobile */}
                    <div className="pt-2 border-t border-slate-100 dark:border-slate-800 flex justify-between items-center text-xs">
                        <Link
                            href="/nang-cap-hoi-vien"
                            onClick={() => setMobileMenuOpen(false)}
                            className="inline-flex items-center gap-1.5 text-indigo-600 dark:text-indigo-400 font-semibold"
                        >
                            <Crown size={14} />
                            <span>Gói Hội viên FinSight</span>
                        </Link>
                    </div>
                </div>
            )}
        </header>
    );
}
