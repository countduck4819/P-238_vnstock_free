"use client";

import { useEffect, useState } from "react";
import { useTheme } from "./ThemeProvider";
import { Sun, Moon } from "lucide-react";

export default function ThemeToggle({ className = "" }: { className?: string }) {
    const { resolvedTheme, toggleTheme } = useTheme();
    const [mounted, setMounted] = useState(false);

    useEffect(() => {
        setMounted(true);
    }, []);

    if (!mounted) {
        return (
            <div className={`w-9 h-9 rounded-lg bg-slate-100 dark:bg-slate-800 animate-pulse ${className}`} />
        );
    }

    const isDark = resolvedTheme === "dark";

    return (
        <button
            type="button"
            onClick={toggleTheme}
            className={`relative p-2 rounded-xl text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100/80 dark:hover:bg-slate-800/80 transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-blue-500/40 border border-slate-200/60 dark:border-slate-800 flex items-center justify-center ${className}`}
            title={isDark ? "Chuyển sang Giao diện Sáng (Light)" : "Chuyển sang Giao diện Tối (Dark)"}
            aria-label="Toggle theme"
        >
            {isDark ? (
                <Sun className="w-4 h-4 text-amber-400 rotate-0 transition-transform duration-300 hover:rotate-45" />
            ) : (
                <Moon className="w-4 h-4 text-indigo-600 rotate-0 transition-transform duration-300 hover:-rotate-12" />
            )}
        </button>
    );
}
