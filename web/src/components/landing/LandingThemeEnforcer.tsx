"use client";

import { useEffect } from "react";

/**
 * Enforces pure Light Theme on the Landing page
 * and restores user's theme when navigating away.
 */
export default function LandingThemeEnforcer() {
    useEffect(() => {
        const root = document.documentElement;
        const hadDark = root.classList.contains("dark");
        
        // Force light mode on landing
        root.classList.remove("dark");
        root.style.colorScheme = "light";

        return () => {
            // Restore user's preference upon leaving /landing
            try {
                const saved = localStorage.getItem("stock-app-theme");
                const isSystemDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
                if (saved === "dark" || (saved === "system" && isSystemDark)) {
                    root.classList.add("dark");
                    root.style.colorScheme = "dark";
                }
            } catch {
                if (hadDark) {
                    root.classList.add("dark");
                    root.style.colorScheme = "dark";
                }
            }
        };
    }, []);

    return null;
}
