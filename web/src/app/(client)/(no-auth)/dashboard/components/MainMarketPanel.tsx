"use client";

import React, { useEffect, useState, useMemo, useCallback } from "react";
import ReactECharts from "echarts-for-react";
import { SECTORS } from "@/const/const";
import RightPanel from "./RightPanel";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import { useTheme } from "@/components/theme/ThemeProvider";
import { useIsMobile } from "@/hooks/use-mobile";
import { RefreshCw, Layers, CheckCircle2 } from "lucide-react";
import { pythonApiUrl } from "@/utils/pythonApi";

// Dữ liệu tạm cố định (0ms) khi người dùng chưa có bộ nhớ đệm cache
const DEFAULT_STOCK_MAP: Record<string, { weight: number; change: number }> = {
    // Tài chính / Ngân hàng / Chứng khoán
    VCB: { weight: 68, change: 1.20 },
    BID: { weight: 62, change: 0.45 },
    CTG: { weight: 60, change: 1.85 },
    TCB: { weight: 58, change: 2.10 },
    MBB: { weight: 56, change: -0.60 },
    VPB: { weight: 54, change: 0.80 },
    ACB: { weight: 52, change: 1.55 },
    STB: { weight: 50, change: -1.25 },
    HDB: { weight: 48, change: 0.40 },
    SHB: { weight: 46, change: 0.00 },
    SSI: { weight: 56, change: 2.35 },
    VND: { weight: 48, change: 1.70 },
    VIX: { weight: 46, change: 3.10 },
    VCI: { weight: 44, change: 0.90 },
    HCM: { weight: 42, change: 1.45 },
    VDS: { weight: 38, change: -0.80 },
    ORS: { weight: 36, change: 0.50 },
    EVS: { weight: 35, change: 0.00 },

    // Bất động sản
    VHM: { weight: 66, change: 0.90 },
    VIC: { weight: 64, change: -0.45 },
    VRE: { weight: 52, change: 1.10 },
    NVL: { weight: 48, change: -2.15 },
    PDR: { weight: 46, change: 1.85 },
    DIG: { weight: 48, change: 2.40 },
    DXG: { weight: 46, change: 1.20 },
    KDH: { weight: 44, change: 0.60 },
    NLG: { weight: 42, change: 1.50 },
    CEO: { weight: 42, change: -1.10 },
    TCH: { weight: 40, change: 0.80 },
    SCR: { weight: 37, change: -0.75 },
    LDG: { weight: 36, change: -3.20 },
    DLG: { weight: 35, change: 0.00 },

    // Thép & Vật liệu
    HPG: { weight: 66, change: 1.95 },
    GVR: { weight: 54, change: 2.10 },
    DGC: { weight: 52, change: 3.40 },
    HSG: { weight: 46, change: 1.40 },
    NKG: { weight: 44, change: 1.15 },
    DPM: { weight: 42, change: -0.65 },
    DCM: { weight: 42, change: 0.45 },
    BFC: { weight: 38, change: 1.20 },
    AAA: { weight: 36, change: -0.80 },
    PLC: { weight: 35, change: 0.00 },

    // Công nghệ
    FPT: { weight: 68, change: 1.39 },
    VTP: { weight: 48, change: 1.80 },
    CMG: { weight: 44, change: 0.75 },
    ELC: { weight: 38, change: -1.10 },
    SAM: { weight: 36, change: -0.50 },
    ITD: { weight: 35, change: 0.00 },

    // Bán lẻ & Tiêu dùng
    VNM: { weight: 66, change: -0.32 },
    MWG: { weight: 64, change: 2.85 },
    MSN: { weight: 60, change: 1.60 },
    SAB: { weight: 52, change: -0.35 },
    PNJ: { weight: 50, change: 1.90 },
    KDC: { weight: 42, change: 0.20 },
    HAG: { weight: 44, change: 3.60 },
    QNS: { weight: 40, change: 0.80 },
    BHN: { weight: 37, change: -0.50 },
    TLG: { weight: 35, change: 0.00 },

    // Công nghiệp
    GEX: { weight: 54, change: 2.10 },
    GMD: { weight: 50, change: 1.30 },
    VCG: { weight: 48, change: 0.90 },
    HHV: { weight: 44, change: -0.70 },
    CII: { weight: 44, change: 1.45 },
    PC1: { weight: 42, change: 0.50 },
    HAH: { weight: 40, change: 2.80 },
    VSC: { weight: 38, change: -0.40 },
};

function getStockColor(change: number) {
    if (change >= 6.8) return "#a855f7"; // Tím trần
    if (change >= 2.0) return "#10b981"; // Xanh lá đậm (Tăng mạnh)
    if (change > 0.0) return "#34d399"; // Xanh lá sáng (Tăng nhẹ)
    if (change <= -6.8) return "#06b6d4"; // Xanh lơ sàn
    if (change <= -2.0) return "#ef4444"; // Đỏ đậm (Giảm mạnh)
    if (change < 0.0) return "#f87171"; // Đỏ nhạt (Giảm nhẹ)
    return "#eab308"; // Vàng tham chiếu
}

function buildInitialData() {
    return SECTORS.map((sector) => {
        const children = sector.stocks.map((symbol) => {
            const info = DEFAULT_STOCK_MAP[symbol] || {
                weight: 42,
                change: 0,
            };
            const change = info.change;
            const color = getStockColor(change);
            const sign = change > 0 ? "+" : "";

            return {
                symbol,
                name: `${symbol}\n${sign}${change.toFixed(2)}%`,
                value: info.weight,
                change,
                itemStyle: { color },
            };
        });

        return {
            name: sector.name,
            children,
        };
    });
}

const CACHE_KEY = "finsight_market_heatmap_v13";
const CACHE_TIME_KEY = "finsight_market_heatmap_time_v13";
const CACHE_TTL_MS = 60 * 1000; // 60 seconds

export default function MarketHeatmap() {
    const router = useRouter();

    // 1. Tầng 1: Lấy ngay từ Cache nếu có, chưa có thì lấy bản tạm Fixed (0ms, không loading)
    const [data, setData] = useState<any[]>(() => {
        if (typeof window !== "undefined") {
            try {
                const cached = sessionStorage.getItem(CACHE_KEY);
                if (cached) {
                    return JSON.parse(cached);
                }
            } catch {
                // Ignore
            }
        }
        return buildInitialData();
    });

    const [isSyncing, setIsSyncing] = useState<boolean>(false);
    const [syncedCount, setSyncedCount] = useState<number>(0);
    const [selectedSector, setSelectedSector] = useState<string>("all");
    const [navigatingSymbol, setNavigatingSymbol] = useState<string | null>(null);
    const { resolvedTheme } = useTheme();
    const isDark = resolvedTheme === "dark";
    // Trên điện thoại ô cổ phiếu rất nhỏ: thu nhỏ chữ để mã và % không tràn ra ngoài ô.
    const isMobile = useIsMobile();

    const allSymbols = useMemo(
        () => Array.from(new Set(SECTORS.flatMap((s) => s.stocks))),
        [],
    );
    const totalStocks = allSymbols.length;

    // Cập nhật từng ô cổ phiếu trực tiếp tại chỗ (In-place Hot Swapping)
    const patchStocksWithMap = useCallback((liveMap: Record<string, number>) => {
        setData((prevData) =>
            SECTORS.map((sector) => {
                const children = sector.stocks.map((symbol) => {
                    const defaultInfo = DEFAULT_STOCK_MAP[symbol] || {
                        weight: 42,
                        change: 0,
                    };
                    const change =
                        liveMap[symbol] !== undefined
                            ? liveMap[symbol]
                            : defaultInfo.change;
                    const color = getStockColor(change);
                    const sign = change > 0 ? "+" : "";

                    return {
                        symbol,
                        name: `${symbol}\n${sign}${change.toFixed(2)}%`,
                        value: defaultInfo.weight,
                        change,
                        itemStyle: { color },
                    };
                });

                return {
                    name: sector.name,
                    children,
                };
            }),
        );
    }, []);

    // 2. Tầng 2: Chạy ngầm cuốn chiếu từng mã một - Thay thế trực tiếp không che màn hình
    const runBackgroundSync = useCallback(
        async (force = false) => {
            if (typeof window !== "undefined" && !force) {
                const cachedTime = sessionStorage.getItem(CACHE_TIME_KEY);
                if (cachedTime && Date.now() - Number(cachedTime) < CACHE_TTL_MS) {
                    // Cache còn mới, không cần đồng bộ lại
                    return;
                }
            }

            setIsSyncing(true);
            const liveMap: Record<string, number> = {};
            let count = 0;

            try {
                // Đợt 1: Lấy nhanh gói tổng quan từ Backend nếu có (< 10ms)
                try {
                    const res = await fetch(`/api/stocks/overview`);
                    if (res.ok) {
                        const json = await res.json();
                        const overviewData = json?.data || json;
                        if (
                            overviewData &&
                            typeof overviewData === "object" &&
                            Object.keys(overviewData).length > 0
                        ) {
                            Object.entries(overviewData).forEach(
                                ([sym, val]: [string, any]) => {
                                    if (val && typeof val.change === "number") {
                                        liveMap[sym] = val.change;
                                    }
                                },
                            );
                            count = Object.keys(liveMap).length;
                            setSyncedCount(count);
                            patchStocksWithMap(liveMap);
                        }
                    }
                } catch {
                    // Ignore
                }

                // Đợt 2: Cuốn chiếu từng nhóm mã còn lại để cập nhật nóng tại chỗ
                const BATCH_SIZE = 8;
                const remaining = allSymbols.filter(
                    (sym) => liveMap[sym] === undefined,
                );
                const toFetch =
                    remaining.length > 0 ? remaining : allSymbols.slice(0, 24);

                for (let i = 0; i < toFetch.length; i += BATCH_SIZE) {
                    const batch = toFetch.slice(i, i + BATCH_SIZE);

                    await Promise.allSettled(
                        batch.map(async (sym) => {
                            try {
                                let res = await fetch(`/api/stocks/candle/${sym}`);
                                if (!res.ok) {
                                    res = await fetch(pythonApiUrl(`/stock/${sym}`));
                                }
                                if (res.ok) {
                                    const raw = await res.json();
                                    const rows = Array.isArray(raw)
                                        ? raw
                                        : raw?.data || [];
                                    if (rows.length >= 2) {
                                        const last = rows[rows.length - 1];
                                        const prev = rows[rows.length - 2];
                                        const lastClose = Number(last?.close || 0);
                                        const prevClose = Number(prev?.close || 0);
                                        if (lastClose > 0 && prevClose > 0) {
                                            liveMap[sym] = Number(
                                                (
                                                    ((lastClose - prevClose) /
                                                        prevClose) *
                                                    100
                                                ).toFixed(2),
                                            );
                                        }
                                    }
                                }
                            } catch {
                                // Ignore
                            } finally {
                                count = Math.min(totalStocks, count + 1);
                            }
                        }),
                    );

                    setSyncedCount(count);
                    patchStocksWithMap(liveMap);
                    await new Promise((r) => setTimeout(r, 40));
                }

                // 3. Tầng 3: Ghi nhớ vào cache để lần sau mở lên lập tức
                if (typeof window !== "undefined") {
                    const finalData = SECTORS.map((sector) => ({
                        name: sector.name,
                        children: sector.stocks.map((symbol) => {
                            const defaultInfo = DEFAULT_STOCK_MAP[symbol] || {
                                weight: 42,
                                change: 0,
                            };
                            const change =
                                liveMap[symbol] !== undefined
                                    ? liveMap[symbol]
                                    : defaultInfo.change;
                            const color = getStockColor(change);
                            const sign = change > 0 ? "+" : "";

                            return {
                                symbol,
                                name: `${symbol}\n${sign}${change.toFixed(2)}%`,
                                value: defaultInfo.weight,
                                change,
                                itemStyle: { color },
                            };
                        }),
                    }));
                    sessionStorage.setItem(CACHE_KEY, JSON.stringify(finalData));
                    sessionStorage.setItem(CACHE_TIME_KEY, String(Date.now()));
                }
            } catch {
                // Ignore
            } finally {
                setIsSyncing(false);
            }
        },
        [allSymbols, patchStocksWithMap, totalStocks],
    );

    useEffect(() => {
        runBackgroundSync(false);
    }, [runBackgroundSync]);

    // Filter by Sector
    const filteredData = useMemo(() => {
        if (selectedSector === "all") return data;
        return data.filter((sec) => sec.name === selectedSector);
    }, [data, selectedSector]);

    // ECharts option config
    const option = useMemo(() => {
        return {
            tooltip: {
                trigger: "item",
                backgroundColor: isDark
                    ? "rgba(15, 23, 42, 0.95)"
                    : "rgba(255, 255, 255, 0.95)",
                borderColor: isDark ? "#334155" : "#e2e8f0",
                textStyle: {
                    color: isDark ? "#f8fafc" : "#0f172a",
                    fontSize: 12,
                },
                formatter: (p: any) => {
                    const sym = p.data?.symbol;
                    if (!sym) {
                        return "";
                    }
                    const c = p.data?.change;
                    const sign = (c ?? 0) > 0 ? "+" : "";
                    const color = getStockColor(c ?? 0);
                    return `
                        <div style="font-weight:bold; font-size:13px; margin-bottom:2px;">${sym}</div>
                        <div style="display:flex; align-items:center; gap:6px;">
                            <span>Biến động:</span>
                            <span style="color:${color}; font-weight:bold;">${sign}${(c ?? 0).toFixed(2)}%</span>
                        </div>
                        <div style="font-size:10px; opacity:0.75; margin-top:4px;">Click để xem biểu đồ & phân tích chi tiết</div>
                    `;
                },
            },
            animation: true,
            animationDuration: 400,
            animationDurationUpdate: 500,
            animationEasing: "cubicOut",
            animationEasingUpdate: "cubicOut",
            series: [
                {
                    type: "treemap",
                    left: 0,
                    top: 0,
                    right: 0,
                    bottom: 0,
                    width: "100%",
                    height: "100%",
                    animation: true,
                    animationDuration: 400,
                    animationDurationUpdate: 500,
                    animationEasing: "cubicOut",
                    animationEasingUpdate: "cubicOut",
                    roam: false,
                    nodeClick: false,
                    breadcrumb: { show: false },
                    squareRatio: 0.5 * (1 + Math.sqrt(5)),
                    levels: [
                        // Cấp 0: Root - Tắt hoàn toàn upperLabel để không bị thanh trống ở đỉnh
                        {
                            itemStyle: {
                                borderColor: "transparent",
                                borderWidth: 0,
                                gapWidth: 3,
                            },
                            upperLabel: {
                                show: false,
                            },
                        },
                        // Cấp 1: Tiêu đề từng ngành (Tài chính, Bất động sản,...)
                        {
                            itemStyle: {
                                borderColor: isDark ? "#1e293b" : "#e2e8f0",
                                borderWidth: 2,
                                gapWidth: 2,
                            },
                            upperLabel: {
                                show: true,
                                height: 26,
                                color: isDark ? "#f1f5f9" : "#0f172a",
                                backgroundColor: isDark ? "#0f172a" : "#f1f5f9",
                                fontSize: 12,
                                fontWeight: "bold",
                                padding: [2, 8],
                                borderColor: isDark ? "#1e293b" : "#e2e8f0",
                                borderWidth: 1,
                                borderRadius: 4,
                            },
                        },
                        // Cấp 2: Từng ô cổ phiếu con
                        {
                            itemStyle: {
                                borderColor: isDark ? "#090d16" : "#ffffff",
                                borderWidth: 1.5,
                                gapWidth: 1.5,
                                borderRadius: 3,
                            },
                            label: {
                                show: true,
                                position: "inside",
                                // "hidden" không cắt rich text nên chữ tràn sang ô bên cạnh;
                                // "truncate" cắt gọn trong ô (ô quá nhỏ thì chỉ hiện phần vừa).
                                overflow: "truncate",
                                ellipsis: "",
                                rich: {
                                    ticker: {
                                        fontSize: isMobile ? 11 : 14,
                                        fontWeight: "bold",
                                        color: "#ffffff",
                                        align: "center",
                                        lineHeight: isMobile ? 14 : 18,
                                    },
                                    change: {
                                        fontSize: isMobile ? 9 : 11,
                                        fontWeight: "bold",
                                        color: "rgba(255, 255, 255, 0.95)",
                                        align: "center",
                                        lineHeight: isMobile ? 11 : 14,
                                    },
                                },
                                formatter: (params: any) => {
                                    const sym =
                                        params.data?.symbol ||
                                        (params.name || "").split("\n")[0];
                                    const c = params.data?.change;
                                    if (c === undefined || c === null) {
                                        return `{ticker|${sym}}`;
                                    }
                                    const sign = c > 0 ? "+" : "";
                                    return `{ticker|${sym}}\n{change|${sign}${c.toFixed(2)}%}`;
                                },
                            },
                        },
                    ],
                    data: filteredData,
                },
            ],
        };
    }, [filteredData, isDark, isMobile]);

    return (
        <div className="min-h-screen lg:h-[calc(100vh-4.6rem)] lg:min-h-0 lg:overflow-hidden bg-slate-50/50 dark:bg-slate-950 text-slate-900 dark:text-white transition-colors flex flex-col">
            <main className="max-w-[95vw] 2xl:max-w-[1600px] w-full mx-auto px-2 sm:px-4 py-2.5 sm:py-3 flex flex-col lg:h-full lg:overflow-hidden">
                {/* Top Control Bar: Title + Status + Legend + Refresh */}
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2.5 bg-white dark:bg-slate-900 p-2.5 sm:p-3 rounded-2xl border border-slate-200/80 dark:border-slate-800 shadow-xs shrink-0">
                    <div className="flex items-center gap-2.5">
                        <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-600 text-white flex items-center justify-center shadow-xs shadow-indigo-500/25 shrink-0">
                            <Layers className="w-4 h-4" />
                        </div>
                        <div>
                            <div className="flex items-center gap-2">
                                <h1 className="text-sm sm:text-base font-bold text-slate-900 dark:text-white">
                                    Bản đồ nhiệt Dòng tiền (Market Heatmap)
                                </h1>
                                {isSyncing ? (
                                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border border-indigo-500/20 animate-pulse">
                                        <RefreshCw size={10} className="animate-spin" />
                                        Đang đồng bộ ngầm ({syncedCount}/{totalStocks})
                                    </span>
                                ) : (
                                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                                        Realtime
                                    </span>
                                )}
                            </div>
                            <p className="text-[11px] text-slate-500 dark:text-slate-400">
                                Trực quan hóa biến động và dòng tiền theo từng
                                nhóm ngành trên thị trường chứng khoán Việt Nam
                            </p>
                        </div>
                    </div>

                    {/* Color Legend & Refresh Action */}
                    <div className="flex items-center gap-2.5 text-xs">
                        {/* Legend */}
                        <div className="hidden md:flex items-center gap-1.5 bg-slate-50 dark:bg-slate-800/60 px-2.5 py-1 rounded-xl border border-slate-200/80 dark:border-slate-800">
                            <span className="text-[10.5px] font-medium text-slate-500 dark:text-slate-400 mr-0.5">
                                Quy ước màu:
                            </span>
                            <span className="flex items-center gap-1 text-[10.5px] font-semibold text-purple-600 dark:text-purple-400">
                                <span className="w-2 h-2 rounded-xs bg-[#a855f7]" />{" "}
                                Trần
                            </span>
                            <span className="flex items-center gap-1 text-[10.5px] font-semibold text-emerald-600 dark:text-emerald-400 ml-0.5">
                                <span className="w-2 h-2 rounded-xs bg-[#10b981]" />{" "}
                                Tăng
                            </span>
                            <span className="flex items-center gap-1 text-[10.5px] font-semibold text-amber-600 dark:text-amber-400 ml-0.5">
                                <span className="w-2 h-2 rounded-xs bg-[#eab308]" />{" "}
                                Tham chiếu
                            </span>
                            <span className="flex items-center gap-1 text-[10.5px] font-semibold text-rose-600 dark:text-rose-400 ml-0.5">
                                <span className="w-2 h-2 rounded-xs bg-[#ef4444]" />{" "}
                                Giảm
                            </span>
                            <span className="flex items-center gap-1 text-[10.5px] font-semibold text-cyan-600 dark:text-cyan-400 ml-0.5">
                                <span className="w-2 h-2 rounded-xs bg-[#06b6d4]" />{" "}
                                Sàn
                            </span>
                        </div>

                        {/* Refresh Button */}
                        <button
                            onClick={() => runBackgroundSync(true)}
                            disabled={isSyncing}
                            className="flex items-center gap-1.5 px-3 py-1 rounded-xl bg-indigo-50 dark:bg-indigo-950/60 hover:bg-indigo-100 dark:hover:bg-indigo-900/60 text-indigo-600 dark:text-indigo-300 text-xs font-semibold transition-all cursor-pointer disabled:opacity-60"
                        >
                            <RefreshCw
                                size={12}
                                className={isSyncing ? "animate-spin" : ""}
                            />
                            <span>
                                {isSyncing ? "Đang đồng bộ..." : "Làm mới"}
                            </span>
                        </button>
                    </div>
                </div>

                {/* Sector Filter Tabs */}
                <div className="mb-2 flex items-center gap-1.5 overflow-x-auto pb-1 no-scrollbar shrink-0">
                    <button
                        onClick={() => setSelectedSector("all")}
                        className={cn(
                            "px-3 py-1 rounded-xl text-xs font-semibold shrink-0 transition-all cursor-pointer",
                            selectedSector === "all"
                                ? "bg-indigo-600 text-white shadow-xs shadow-indigo-500/25"
                                : "bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 border border-slate-200/80 dark:border-slate-800",
                        )}
                    >
                        Tất cả ({SECTORS.reduce((acc, s) => acc + s.stocks.length, 0)})
                    </button>
                    {SECTORS.map((sec) => (
                        <button
                            key={sec.name}
                            onClick={() => setSelectedSector(sec.name)}
                            className={cn(
                                "px-3 py-1 rounded-xl text-xs font-semibold shrink-0 transition-all cursor-pointer",
                                selectedSector === sec.name
                                    ? "bg-indigo-600 text-white shadow-xs shadow-indigo-500/25"
                                    : "bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 border border-slate-200/80 dark:border-slate-800",
                            )}
                        >
                            {sec.name} ({sec.stocks.length})
                        </button>
                    ))}
                </div>

                {/* Main Content Grid: Heatmap (Left) + RightPanel (Right) */}
                <section className="grid grid-cols-1 lg:grid-cols-[1fr_360px] xl:grid-cols-[1fr_390px] gap-3.5 items-stretch lg:flex-1 lg:min-h-0 lg:overflow-hidden">
                    {/* Left: Heatmap Canvas Card - Hiển thị 100% không loading */}
                    <div className="w-full h-[520px] sm:h-[620px] lg:h-full bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 shadow-xs overflow-hidden p-1 sm:p-1.5 flex flex-col shrink-0">
                        <div className="relative w-full h-full flex-1 rounded-xl overflow-hidden bg-white dark:bg-slate-900">
                            <ReactECharts
                                key={`echarts-heatmap-${isDark ? "dark" : "light"}`}
                                option={option}
                                notMerge={false}
                                lazyUpdate={true}
                                style={{
                                    height: "100%",
                                    width: "100%",
                                    minHeight: "480px",
                                }}
                                onEvents={{
                                    click: (params: any) => {
                                        // Chỉ cho phép điều hướng khi click vào từng ô cổ phiếu có trường `symbol`
                                        // Bỏ qua hoàn toàn khi click vào tiêu đề nhóm ngành (ví dụ "Tài chính", "Bất động sản",...)
                                        const sym = params?.data?.symbol;
                                        if (!sym || typeof sym !== "string") {
                                            return;
                                        }

                                        const cleanSym = sym.trim().toUpperCase();
                                        if (cleanSym && cleanSym.length >= 3) {
                                            setNavigatingSymbol(cleanSym);
                                            router.push(
                                                `/ma-chung-khoan/${cleanSym.toLowerCase()}`,
                                            );
                                        }
                                    },
                                }}
                            />
                        </div>
                    </div>

                    {/* Right: Featured News Panel (Tự động kéo dài trên Mobile, cố định trọn màn hình trên Desktop) */}
                    <div className="w-full h-auto lg:h-full lg:min-h-0 flex flex-col">
                        <RightPanel />
                    </div>
                </section>
            </main>

            {/* Instant Click Transition HUD */}
            {navigatingSymbol && (
                <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 px-4 py-2 bg-slate-900/95 dark:bg-slate-900/95 text-white border border-indigo-500/40 rounded-2xl shadow-2xl backdrop-blur-md flex items-center gap-3 animate-pulse">
                    <div className="w-4 h-4 rounded-full border-2 border-indigo-400 border-t-transparent animate-spin" />
                    <span className="text-xs font-semibold">
                        Đang mở phân tích mã <span className="text-indigo-400 font-bold font-mono">{navigatingSymbol}</span>...
                    </span>
                </div>
            )}
        </div>
    );
}
