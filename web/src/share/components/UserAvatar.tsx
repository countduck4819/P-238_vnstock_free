"use client";

import React, { useState } from "react";
import { cn } from "@/lib/utils";

interface UserAvatarProps {
    src?: string | null;
    name?: string | null;
    email?: string | null;
    size?: number; // size in px, e.g. 32, 48
    className?: string;
    textClassName?: string;
}

// Deterministic vibrant gradient palettes inspired by Google/Gmail user avatars
const AVATAR_GRADIENTS = [
    "from-blue-500 to-indigo-600",
    "from-emerald-500 to-teal-600",
    "from-purple-500 to-pink-600",
    "from-amber-500 to-orange-600",
    "from-rose-500 to-red-600",
    "from-cyan-500 to-blue-600",
    "from-violet-500 to-purple-600",
    "from-teal-500 to-emerald-600",
];

function getGradientKey(str?: string | null): string {
    if (!str) return AVATAR_GRADIENTS[0];
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        hash = str.charCodeAt(i) + ((hash << 5) - hash);
    }
    const index = Math.abs(hash) % AVATAR_GRADIENTS.length;
    return AVATAR_GRADIENTS[index];
}

function getInitials(name?: string | null, email?: string | null): string {
    const text = (name || email || "").trim();
    if (!text) return "U";
    const parts = text.split(/\s+/).filter(Boolean);
    if (parts.length >= 2) {
        return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    }
    return text.substring(0, text.length >= 2 && !text.includes("@") ? 2 : 1).toUpperCase();
}

export default function UserAvatar({
    src,
    name,
    email,
    size = 32,
    className,
    textClassName,
}: UserAvatarProps) {
    const [imageError, setImageError] = useState(false);
    const gradient = getGradientKey(name || email);
    const initials = getInitials(name, email);

    // If a valid image URL is provided and not errored
    if (src && !imageError && (src.startsWith("http") || src.startsWith("/img") || src.startsWith("/icons"))) {
        return (
            <div
                style={{ width: size, height: size }}
                className={cn(
                    "relative rounded-full overflow-hidden shrink-0 border border-slate-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 shadow-xs",
                    className
                )}
            >
                <img
                    src={src}
                    alt={name || "User Avatar"}
                    className="w-full h-full object-cover"
                    onError={() => setImageError(true)}
                />
            </div>
        );
    }

    // Google / Gmail round letter avatar with vibrant gradient
    return (
        <div
            style={{ width: size, height: size }}
            className={cn(
                "relative rounded-full overflow-hidden shrink-0 flex items-center justify-center font-bold text-white shadow-sm select-none uppercase tracking-wider bg-gradient-to-br border border-white/20",
                gradient,
                className
            )}
            title={name || email || "User"}
        >
            <span
                style={{ fontSize: Math.max(11, Math.floor(size * 0.44)) }}
                className={cn("leading-none font-semibold text-white drop-shadow-xs", textClassName)}
            >
                {initials}
            </span>
        </div>
    );
}
