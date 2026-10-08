"use client";

import React from "react";
import { cn } from "@/lib/utils";

interface BrandLogoProps {
    className?: string;
    size?: "sm" | "md" | "lg" | "xl";
    variant?: "default" | "white" | "dark";
    showText?: boolean;
    withFrame?: boolean;
}

export default function BrandLogo({
    className = "",
    size = "md",
    variant = "default",
    showText = true,
}: BrandLogoProps) {
    const sizeMap = {
        sm: { height: 38, width: 145 },
        md: { height: 50, width: 195 },
        lg: { height: 64, width: 255 },
        landing: { height: 62, width: 245 },
        xl: { height: 80, width: 320 },
    };

    const currentSize = sizeMap[size] || sizeMap.md;

    // Unique IDs for SVG gradients to prevent DOM collisions
    const gradientIdSight = `grad-sight-${size}-${variant}`;
    const gradientIdLine = `grad-line-${size}-${variant}`;
    const gradientIdArrow = `grad-arrow-${size}-${variant}`;
    const gradientIdUnderline = `grad-under-${size}-${variant}`;

    return (
        <div
            className={cn(
                "inline-flex items-center select-none shrink-0 group transition-transform duration-200 hover:scale-[1.03] py-0.5",
                className
            )}
        >
            <svg
                viewBox="0 0 248 80"
                style={{ height: currentSize.height, width: "auto", overflow: "visible" }}
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
                className="drop-shadow-xs"
            >
                <defs>
                    {/* Gradient for "sight" text: Cyan -> Violet/Purple -> Champagne Gold */}
                    <linearGradient id={gradientIdSight} x1="0%" y1="0%" x2="100%" y2="0%">
                        <stop offset="0%" stopColor="#38bdf8" />
                        <stop offset="25%" stopColor="#6366f1" />
                        <stop offset="60%" stopColor="#a855f7" />
                        <stop offset="100%" stopColor="#f59e0b" />
                    </linearGradient>

                    {/* Gradient for financial chart line */}
                    <linearGradient id={gradientIdLine} x1="0%" y1="100%" x2="100%" y2="0%">
                        <stop offset="0%" stopColor="#06b6d4" />
                        <stop offset="50%" stopColor="#818cf8" />
                        <stop offset="100%" stopColor="#f59e0b" />
                    </linearGradient>

                    {/* Gradient for Arrowhead */}
                    <linearGradient id={gradientIdArrow} x1="0%" y1="100%" x2="100%" y2="0%">
                        <stop offset="0%" stopColor="#f59e0b" />
                        <stop offset="100%" stopColor="#fde047" />
                    </linearGradient>

                    {/* Gradient for Underline */}
                    <linearGradient id={gradientIdUnderline} x1="0%" y1="0%" x2="100%" y2="0%">
                        <stop offset="0%" stopColor="#06b6d4" />
                        <stop offset="50%" stopColor="#818cf8" />
                        <stop offset="100%" stopColor="#f59e0b" stopOpacity="0.7" />
                    </linearGradient>
                </defs>

                {/* 1. Left Vertical Accent Bar */}
                <path
                    d="M 4 16 L 4 70"
                    stroke={`url(#${gradientIdUnderline})`}
                    strokeWidth="3.2"
                    strokeLinecap="round"
                    className="opacity-80"
                />

                {/* 2. Horizontal Underline beneath 'fin' */}
                <path
                    d="M 12 70 L 126 70"
                    stroke={`url(#${gradientIdUnderline})`}
                    strokeWidth="3.2"
                    strokeLinecap="round"
                />

                {/* 3. Text 'finsight' (Bold, enlarged, prominent brand wordmark) */}
                <text
                    x="12"
                    y="62"
                    style={{
                        fontFamily: "system-ui, -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', Roboto, sans-serif",
                        fontSize: "64px",
                        fontWeight: 900,
                        letterSpacing: "-2px",
                    }}
                >
                    {/* 'fin' part: High contrast deep Slate in Light Mode / Pure White in Dark Mode */}
                    <tspan
                        className={cn(
                            "font-black",
                            variant === "white" || variant === "dark"
                                ? "fill-white"
                                : "fill-slate-900 dark:fill-white"
                        )}
                    >
                        fin
                    </tspan>

                    {/* 'sight' part: Rich multi-stop vibrant gradient */}
                    <tspan
                        fill={`url(#${gradientIdSight})`}
                        className="font-black"
                    >
                        sight
                    </tspan>
                </text>

                {/* 4. Financial Upward Trend Chart Line */}
                <path
                    d="M 8 59 L 32 46 L 46 52 L 72 26 L 84 34 L 114 10"
                    stroke={`url(#${gradientIdLine})`}
                    strokeWidth="3.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                />

                {/* 5. Glowing Node Dots */}
                <circle cx="32" cy="46" r="3.8" fill="#38bdf8" />
                <circle cx="46" cy="52" r="3.2" fill="#38bdf8" />
                <circle cx="72" cy="26" r="3.8" fill="#818cf8" />
                <circle cx="84" cy="34" r="3.8" fill="#a855f7" />

                {/* 6. Growth Arrowhead at the Peak */}
                <g transform="translate(114, 10) rotate(50)">
                    <path
                        d="M -5.5 11 L 0 0 L 5.5 11 L 0 8 Z"
                        fill={`url(#${gradientIdArrow})`}
                    />
                </g>
            </svg>
        </div>
    );
}
