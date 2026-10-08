"use client";

import { useEffect, useRef } from "react";
import { useTheme } from "@/components/theme/ThemeProvider";

export default function LeftPanel() {
    const containerRef = useRef<HTMLDivElement | null>(null);
    const { resolvedTheme } = useTheme();
    const isDark = resolvedTheme === "dark";

    useEffect(() => {
        if (!containerRef.current) return;

        // Clear existing widget content before re-rendering
        containerRef.current.innerHTML = "";

        const widgetDiv = document.createElement("div");
        widgetDiv.id = "tradingview-overview";
        widgetDiv.className = "h-[43.75rem] w-full";
        containerRef.current.appendChild(widgetDiv);

        const script = document.createElement("script");
        script.src =
            "https://s3.tradingview.com/external-embedding/embed-widget-market-overview.js";
        script.async = true;
        script.innerHTML = JSON.stringify({
            colorTheme: isDark ? "dark" : "light",
            dateRange: "3M",
            showChart: true,
            locale: "vi",
            width: "100%",
            height: 700,
            largeChartUrl: "",
            isTransparent: false,
            showSymbolLogo: true,
            showFloatingTooltip: false,
            plotLineColorGrowing: "rgba(41, 98, 255, 1)",
            plotLineColorFalling: "rgba(255, 0, 0, 1)",
            gridLineColor: isDark ? "rgba(240, 243, 250, 0.06)" : "rgba(240, 243, 250, 1)",
            scaleFontColor: isDark ? "rgba(160, 163, 174, 1)" : "rgba(120, 123, 134, 1)",
            belowLineFillColorGrowing: "rgba(41, 98, 255, 0.12)",
            belowLineFillColorFalling: "rgba(255, 0, 0, 0.12)",
            tabs: [
                {
                    title: "Việt Nam",
                    symbols: [
                        { s: "HOSE:VNINDEX", d: "VNINDEX" },
                        { s: "HNX:HNXINDEX", d: "HNXINDEX" },
                        { s: "UPCOM:UPINDEX", d: "UPINDEX" },
                        { s: "HOSE:VN30", d: "VN30" },
                        { s: "HNX:VN30F1M", d: "VN30F1M" },
                    ],
                    originalTitle: "Việt Nam",
                },
                {
                    title: "Châu Mỹ",
                    symbols: [
                        { s: "NASDAQ:NDX", d: "Nasdaq 100" },
                        { s: "SP:SPX", d: "S&P 500" },
                        { s: "DJI:DJI", d: "Dow Jones" },
                    ],
                    originalTitle: "Châu Mỹ",
                },
                {
                    title: "Châu Âu",
                    symbols: [
                        { s: "INDEX:CAC40", d: "CAC 40" },
                        { s: "INDEX:DAX", d: "DAX" },
                        { s: "INDEX:FTSE", d: "FTSE 100" },
                    ],
                    originalTitle: "Châu Âu",
                },
                {
                    title: "Châu Á",
                    symbols: [
                        { s: "INDEX:NKY", d: "Nikkei 225" },
                        { s: "INDEX:HSI", d: "Hang Seng" },
                        { s: "INDEX:STI", d: "STI" },
                    ],
                    originalTitle: "Châu Á",
                },
            ],
        });

        containerRef.current.appendChild(script);
    }, [isDark]);

    return (
        <div
            ref={containerRef}
            className="rounded-lg overflow-hidden bg-white dark:bg-slate-900 border border-gray-200 dark:border-slate-800 transition-colors"
        >
            <div id="tradingview-overview" className="h-[43.75rem]" />
        </div>
    );
}
