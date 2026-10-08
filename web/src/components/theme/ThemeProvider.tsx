"use client";

import React, { createContext, useContext, useEffect, useState, useMemo } from "react";

type Theme = "light" | "dark" | "system";
type ResolvedTheme = "light" | "dark";

interface ThemeContextType {
    theme: Theme;
    resolvedTheme: ResolvedTheme;
    setTheme: (theme: Theme) => void;
    toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

const STORAGE_KEY = "stock-app-theme";

export function ThemeProvider({
    children,
    defaultTheme = "system",
}: {
    children: React.ReactNode;
    defaultTheme?: Theme;
}) {
    const [theme, setThemeState] = useState<Theme>(() => {
        if (typeof window === "undefined") return defaultTheme;
        try {
            const saved = localStorage.getItem(STORAGE_KEY) as Theme | null;
            return saved || defaultTheme;
        } catch {
            return defaultTheme;
        }
    });

    const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>("light");
    const [, setMounted] = useState(false);

    // Helper to calculate resolved theme
    const getSystemTheme = (): ResolvedTheme => {
        if (typeof window === "undefined") return "light";
        return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    };

    const applyTheme = (currentTheme: Theme) => {
        if (typeof document === "undefined") return;
        const root = document.documentElement;
        const targetResolved: ResolvedTheme =
            currentTheme === "system" ? getSystemTheme() : currentTheme;

        setResolvedTheme(targetResolved);

        if (targetResolved === "dark") {
            root.classList.add("dark");
            root.style.colorScheme = "dark";
        } else {
            root.classList.remove("dark");
            root.style.colorScheme = "light";
        }
    };

    const setTheme = (newTheme: Theme) => {
        setThemeState(newTheme);
        try {
            localStorage.setItem(STORAGE_KEY, newTheme);
        } catch (e) {
            console.error("Failed to save theme in localStorage", e);
        }
        applyTheme(newTheme);
    };

    const toggleTheme = () => {
        const nextTheme = resolvedTheme === "dark" ? "light" : "dark";
        setTheme(nextTheme);
    };

    const contextValue = useMemo(
        () => ({
            theme,
            resolvedTheme,
            setTheme,
            toggleTheme,
        }),
        [theme, resolvedTheme]
    );

    useEffect(() => {
        setMounted(true);
        try {
            const saved = (localStorage.getItem(STORAGE_KEY) as Theme) || defaultTheme;
            setThemeState(saved);
            applyTheme(saved);
        } catch {
            applyTheme(defaultTheme);
        }

        // Listen to system theme changes
        const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
        const handleChange = () => {
            const currentSaved = (localStorage.getItem(STORAGE_KEY) as Theme) || theme;
            if (currentSaved === "system") {
                applyTheme("system");
            }
        };

        mediaQuery.addEventListener("change", handleChange);
        return () => mediaQuery.removeEventListener("change", handleChange);
    }, []);

    return (
        <ThemeContext.Provider value={contextValue}>
            {children}
        </ThemeContext.Provider>
    );
}

export function useTheme() {
    const context = useContext(ThemeContext);
    if (!context) {
        // Fallback for components outside ThemeProvider
        return {
            theme: "light" as Theme,
            resolvedTheme: "light" as ResolvedTheme,
            setTheme: () => {},
            toggleTheme: () => {},
        };
    }
    return context;
}
