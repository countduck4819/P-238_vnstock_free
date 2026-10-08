"use client";

import { useEffect, useRef, useState, useMemo, useCallback } from "react";
import {
    createChart,
    ColorType,
    CrosshairMode,
    CandlestickSeries,
    HistogramSeries,
    LineSeries,
    AreaSeries,
    createTextWatermark,
    type CandlestickData,
    type IChartApi,
    type ISeriesApi,
} from "lightweight-charts";
import { useAppDispatch, useAppSelector } from "@/redux/hooks";
import {
    fetchStockCandleData,
    fetchStocks,
} from "@/store/stock-symbols/stock-symbols.api";
import { useParams, useRouter } from "next/navigation";
import Loading from "./Loading";
import { useTheme } from "@/components/theme/ThemeProvider";
import {
    Crosshair,
    Ruler,
    TrendingUp,
    Minus,
    Trash2,
    RotateCcw,
    Calendar,
    Eye,
    EyeOff,
    HelpCircle,
} from "lucide-react";

interface Candle {
    time: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
}

interface HoverData {
    time: string;
    open: number;
    high: number;
    low: number;
    close: number;
    change: number;
    percent: number;
    volume: number;
    ma10?: number | null;
    ma50?: number | null;
    ma200?: number | null;
}

interface MeasureResult {
    startPrice: number;
    endPrice: number;
    priceDiff: number;
    percentDiff: number;
    startTime: string;
    endTime: string;
    bars: number;
}

const normalizeData = <T extends { time: string }>(arr: T[]): T[] => {
    const sorted = [...arr].sort((a, b) =>
        a.time > b.time ? 1 : a.time < b.time ? -1 : 0,
    );
    return sorted.filter((v, i, a) => i === 0 || a[i - 1].time !== v.time);
};

function calcMA(data: Candle[], length: number) {
    const result: { time: string; value: number }[] = [];
    for (let i = length - 1; i < data.length; i++) {
        const slice = data.slice(i - length + 1, i + 1);
        const avg =
            slice.reduce((a, b) => a + (b.close || 0), 0) / slice.length;
        result.push({ time: data[i].time, value: avg });
    }
    return result;
}

function formatVolume(v: number): string {
    if (v >= 1_000_000_000) return (v / 1_000_000_000).toFixed(2) + "B";
    if (v >= 1_000_000) return (v / 1_000_000).toFixed(2) + "M";
    if (v >= 1_000) return (v / 1_000).toFixed(1) + "K";
    return v.toLocaleString("vi-VN");
}

type ActiveTool = "cursor" | "measure" | "horizontal" | "trendline";

export default function TradingViewWidget({
    symbol,
    height = 540,
    showDrawingTools = true,
}: {
    symbol?: string;
    height?: number;
    showDrawingTools?: boolean;
}) {
    const router = useRouter();
    const params = useParams();
    const dispatch = useAppDispatch();
    const { stocksSymbolList, stocksFullList, candleData, loading } =
        useAppSelector((state) => state.stockSymbols);
    const stock =
        String(params.stock || "").toUpperCase() || symbol?.toUpperCase() || "VNINDEX";

    const containerRef = useRef<HTMLDivElement>(null);
    const chartRef = useRef<IChartApi | null>(null);
    const candleSeriesRef = useRef<any>(null);
    const priceLinesRef = useRef<any[]>([]);

    // Tool state
    const [activeTool, setActiveTool] = useState<ActiveTool>("cursor");
    const [measurePoints, setMeasurePoints] = useState<any[]>([]);
    const [measureResult, setMeasureResult] = useState<MeasureResult | null>(null);

    // Chart style state
    const [chartType, setChartType] = useState<"candles" | "area">("candles");
    const [showMA10, setShowMA10] = useState(true);
    const [showMA50, setShowMA50] = useState(true);
    const [showMA200, setShowMA200] = useState(true);
    const [showVolume, setShowVolume] = useState(true);
    const [timeframe, setTimeframe] = useState<"1M" | "3M" | "6M" | "1Y" | "ALL">("ALL");

    // Dynamic Hover / Crosshair Legend State
    const [hoverData, setHoverData] = useState<HoverData | null>(null);

    const { resolvedTheme } = useTheme();
    const theme = resolvedTheme;

    const companyInfo = useMemo(() => {
        return stocksFullList.find((s) => s.symbol === stock);
    }, [stocksFullList, stock]);

    const rawCompanyName =
        companyInfo?.org_name || (companyInfo as any)?.organ_name || "";
    const hasDistinctName =
        Boolean(rawCompanyName) &&
        rawCompanyName.trim().toUpperCase() !== stock.trim().toUpperCase() &&
        !rawCompanyName
            .trim()
            .toUpperCase()
            .startsWith(`CHỈ SỐ / CỔ PHIẾU ${stock.trim().toUpperCase()}`) &&
        !rawCompanyName
            .trim()
            .toUpperCase()
            .startsWith(`CỔ PHIẾU ${stock.trim().toUpperCase()}`);

    useEffect(() => {
        if (!stocksSymbolList.length) {
            dispatch(fetchStocks());
        }
    }, [dispatch, stocksSymbolList.length]);

    useEffect(() => {
        if (!stock) return;
        dispatch(fetchStockCandleData(stock));
    }, [dispatch, stock]);

    // Default latest data
    const latestData = useMemo<HoverData | null>(() => {
        if (!candleData || candleData.length === 0) return null;
        const normalized = normalizeData(candleData);
        const last = normalized[normalized.length - 1];
        const prev = normalized[normalized.length - 2] || last;
        const chg = last.close - prev.close;
        const pct = prev.close ? (chg / prev.close) * 100 : 0;

        const ma10Vals = calcMA(normalized, 10);
        const ma50Vals = calcMA(normalized, 50);
        const ma200Vals = calcMA(normalized, 200);

        return {
            time: last.time,
            open: last.open,
            high: last.high,
            low: last.low,
            close: last.close,
            change: chg,
            percent: pct,
            volume: last.volume,
            ma10: ma10Vals[ma10Vals.length - 1]?.value ?? null,
            ma50: ma50Vals[ma50Vals.length - 1]?.value ?? null,
            ma200: ma200Vals[ma200Vals.length - 1]?.value ?? null,
        };
    }, [candleData]);

    const activeToolRef = useRef<ActiveTool>(activeTool);
    useEffect(() => {
        activeToolRef.current = activeTool;
    }, [activeTool]);

    // Build Chart using Lightweight-Charts & Redux Candle Data
    useEffect(() => {
        if (!stock || !containerRef.current) return;
        if (!candleData || candleData.length === 0) return;

        const data = normalizeData(candleData);
        if (data.length === 0) return;

        const isDark = theme === "dark";
        const bg = isDark ? "#0b0f17" : "#ffffff";
        const text = isDark ? "#94a3b8" : "#475569";
        const grid = isDark ? "rgba(30, 41, 59, 0.4)" : "rgba(226, 232, 240, 0.8)";
        const up = "#10b981";
        const down = "#f43f5e";

        containerRef.current.innerHTML = "";

        const chart = createChart(containerRef.current, {
            layout: {
                background: { type: ColorType.Solid, color: bg },
                textColor: text,
                fontFamily: "Inter, sans-serif",
                fontSize: 11,
            },
            grid: {
                vertLines: { color: grid },
                horzLines: { color: grid },
            },
            width: containerRef.current.clientWidth || 800,
            height: height,
            crosshair: {
                mode: CrosshairMode.Normal,
                vertLine: {
                    color: isDark ? "rgba(148, 163, 184, 0.4)" : "rgba(100, 116, 139, 0.4)",
                    width: 1,
                    style: 2,
                    labelBackgroundColor: isDark ? "#1e293b" : "#475569",
                },
                horzLine: {
                    color: isDark ? "rgba(148, 163, 184, 0.4)" : "rgba(100, 116, 139, 0.4)",
                    width: 1,
                    style: 2,
                    labelBackgroundColor: isDark ? "#1e293b" : "#475569",
                },
            },
            rightPriceScale: {
                borderColor: isDark ? "#1e293b" : "#e2e8f0",
                scaleMargins: { top: 0.1, bottom: 0.2 },
            },
            timeScale: {
                borderColor: isDark ? "#1e293b" : "#e2e8f0",
                timeVisible: true,
                secondsVisible: false,
            },
        });
        chartRef.current = chart;

        // Series
        let candleSeries: any = null;
        if (chartType === "candles") {
            candleSeries = chart.addSeries(CandlestickSeries, {
                upColor: up,
                downColor: down,
                borderUpColor: up,
                borderDownColor: down,
                wickUpColor: up,
                wickDownColor: down,
            });
            candleSeries.setData(data);
        } else {
            candleSeries = chart.addSeries(AreaSeries, {
                topColor: "rgba(99, 102, 241, 0.35)",
                bottomColor: "rgba(99, 102, 241, 0.0)",
                lineColor: "#6366f1",
                lineWidth: 2,
            });
            candleSeries.setData(
                data.map((d) => ({
                    time: d.time,
                    value: d.close,
                }))
            );
        }
        candleSeriesRef.current = candleSeries;

        // Volume
        if (showVolume) {
            const volumeSeries = chart.addSeries(HistogramSeries, {
                priceScaleId: "",
                priceLineVisible: false,
            });
            chart.priceScale("").applyOptions({
                scaleMargins: { top: 0.8, bottom: 0 },
            });
            volumeSeries.applyOptions({
                priceFormat: {
                    type: "custom",
                    formatter: (v: number) => formatVolume(v),
                },
            });
            volumeSeries.setData(
                data.map((d) => ({
                    time: d.time,
                    value: d.volume,
                    color: d.close >= d.open ? (isDark ? "rgba(16, 185, 129, 0.45)" : "rgba(16, 185, 129, 0.65)") : (isDark ? "rgba(244, 63, 94, 0.45)" : "rgba(244, 63, 94, 0.65)"),
                }))
            );
        }

        // MA10
        if (showMA10) {
            const ma10Data = calcMA(data, 10);
            chart.addSeries(LineSeries, {
                color: "#818cf8",
                lineWidth: 2,
                lastValueVisible: false,
                priceLineVisible: false,
                title: "MA10",
            }).setData(ma10Data);
        }

        // MA50
        if (showMA50) {
            const ma50Data = calcMA(data, 50);
            chart.addSeries(LineSeries, {
                color: "#38bdf8",
                lineWidth: 2,
                lastValueVisible: false,
                priceLineVisible: false,
                title: "MA50",
            }).setData(ma50Data);
        }

        // MA200
        if (showMA200) {
            const ma200Data = calcMA(data, 200);
            chart.addSeries(LineSeries, {
                color: "#f97316",
                lineWidth: 2,
                lastValueVisible: false,
                priceLineVisible: false,
                title: "MA200",
            }).setData(ma200Data);
        }

        // Watermark
        const pane = chart.panes()[0];
        if (pane) {
            createTextWatermark(pane, {
                horzAlign: "center",
                vertAlign: "center",
                lines: [
                    {
                        text: stock,
                        color: isDark ? "rgba(255,255,255,0.03)" : "rgba(0,0,0,0.03)",
                        fontSize: 120,
                        fontStyle: "bold",
                    },
                ],
            });
        }

        // Crosshair Hover
        const ma10Map = new Map(calcMA(data, 10).map((m) => [m.time, m.value]));
        const ma50Map = new Map(calcMA(data, 50).map((m) => [m.time, m.value]));
        const ma200Map = new Map(calcMA(data, 200).map((m) => [m.time, m.value]));
        const dataMap = new Map(data.map((d, i) => [d.time, { item: d, prev: data[i - 1] || d }]));

        chart.subscribeCrosshairMove((param) => {
            if (!param.time || !param.point) {
                setHoverData((prev) => (prev === null ? prev : null));
                return;
            }

            const timeStr = String(param.time);
            const found = dataMap.get(timeStr);
            if (!found) {
                setHoverData((prev) => (prev === null ? prev : null));
                return;
            }

            const { item: d, prev } = found;
            const chg = d.close - prev.close;
            const pct = prev.close ? (chg / prev.close) * 100 : 0;

            setHoverData((current) => {
                if (current?.time === timeStr) return current;
                return {
                    time: timeStr,
                    open: d.open,
                    high: d.high,
                    low: d.low,
                    close: d.close,
                    change: chg,
                    percent: pct,
                    volume: d.volume,
                    ma10: ma10Map.get(timeStr) ?? null,
                    ma50: ma50Map.get(timeStr) ?? null,
                    ma200: ma200Map.get(timeStr) ?? null,
                };
            });
        });

        // Click Handler for Tools (Horizontal line / Measurement)
        chart.subscribeClick((param) => {
            if (!param.point || !param.time) return;

            const timeStr = String(param.time);
            const found = dataMap.get(timeStr);
            if (!found) return;

            const closeVal = found.item.close;
            const currentTool = activeToolRef.current;

            if (currentTool === "horizontal") {
                // Add horizontal support/resistance line
                if (candleSeriesRef.current) {
                    const priceLine = candleSeriesRef.current.createPriceLine({
                        price: closeVal,
                        color: "#6366f1",
                        lineWidth: 2,
                        lineStyle: 1, // Dotted
                        axisLabelVisible: true,
                        title: `Kháng cự/Hỗ trợ: ${closeVal.toFixed(2)}`,
                    });
                    priceLinesRef.current.push(priceLine);
                }
            } else if (currentTool === "measure") {
                // Measure logic: Point 1 & Point 2
                setMeasurePoints((prev) => {
                    if (prev.length === 0) {
                        return [{ time: timeStr, price: closeVal, index: data.findIndex((d) => d.time === timeStr) }];
                    } else if (prev.length === 1) {
                        const p1 = prev[0];
                        const p2 = { time: timeStr, price: closeVal, index: data.findIndex((d) => d.time === timeStr) };
                        const diff = p2.price - p1.price;
                        const pct = p1.price > 0 ? (diff / p1.price) * 100 : 0;
                        const barsCount = Math.abs(p2.index - p1.index) + 1;

                        setMeasureResult({
                            startPrice: p1.price,
                            endPrice: p2.price,
                            priceDiff: diff,
                            percentDiff: pct,
                            startTime: p1.time,
                            endTime: p2.time,
                            bars: barsCount,
                        });
                        return [];
                    }
                    return [];
                });
            }
        });

        // Apply Timeframes
        if (timeframe === "1M") {
            const lastIdx = data.length - 1;
            const fromIdx = Math.max(0, lastIdx - 22);
            chart.timeScale().setVisibleLogicalRange({ from: fromIdx, to: lastIdx });
        } else if (timeframe === "3M") {
            const lastIdx = data.length - 1;
            const fromIdx = Math.max(0, lastIdx - 66);
            chart.timeScale().setVisibleLogicalRange({ from: fromIdx, to: lastIdx });
        } else if (timeframe === "6M") {
            const lastIdx = data.length - 1;
            const fromIdx = Math.max(0, lastIdx - 132);
            chart.timeScale().setVisibleLogicalRange({ from: fromIdx, to: lastIdx });
        } else if (timeframe === "1Y") {
            const lastIdx = data.length - 1;
            const fromIdx = Math.max(0, lastIdx - 260);
            chart.timeScale().setVisibleLogicalRange({ from: fromIdx, to: lastIdx });
        } else {
            chart.timeScale().fitContent();
        }

        const resizeObserver = new ResizeObserver((entries) => {
            for (const entry of entries) {
                if (entry.contentRect.width > 0 && chartRef.current) {
                    chartRef.current.applyOptions({ width: entry.contentRect.width });
                }
            }
        });
        if (containerRef.current) {
            resizeObserver.observe(containerRef.current);
        }

        return () => {
            resizeObserver.disconnect();
            chart.remove();
        };
    }, [stock, theme, candleData, chartType, showMA10, showMA50, showMA200, showVolume, timeframe]);

    const activeDisplay = hoverData || latestData;

    const handleClearDrawings = () => {
        if (candleSeriesRef.current && priceLinesRef.current.length > 0) {
            priceLinesRef.current.forEach((line) => {
                try {
                    candleSeriesRef.current.removePriceLine(line);
                } catch {}
            });
            priceLinesRef.current = [];
        }
        setMeasurePoints([]);
        setMeasureResult(null);
    };

    const handleResetZoom = useCallback(() => {
        setTimeframe("ALL");
        if (chartRef.current) {
            chartRef.current.timeScale().fitContent();
        }
    }, []);

    // Render seamlessly with in-place skeleton instead of disruptive full-screen overlay

    return (
        <div className="relative w-full rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm overflow-hidden transition-all flex flex-col">
            {/* 1. TOP TOOLBAR & CONTROLS */}
            <div className="px-4 py-3 border-b border-slate-200/80 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-900/90 flex flex-wrap items-center justify-between gap-3">
                {/* Left: Ticker & Chart Type Selector */}
                <div className="flex items-center gap-3">
                    <div className="flex items-center gap-2">
                        <span className="px-2.5 py-1 rounded-lg text-xs font-black bg-indigo-600/10 dark:bg-indigo-500/20 text-indigo-600 dark:text-indigo-400 border border-indigo-500/30 font-mono">
                            {stock}
                        </span>
                        {hasDistinctName && (
                            <span className="hidden sm:inline text-xs font-bold text-slate-700 dark:text-slate-200 truncate max-w-[240px]">
                                {rawCompanyName}
                            </span>
                        )}
                    </div>

                    {/* Chart Type */}
                    <div className="flex items-center bg-slate-200/70 dark:bg-slate-800 p-0.5 rounded-lg text-xs">
                        <button
                            onClick={() => setChartType("candles")}
                            className={`px-2.5 py-1 rounded-md font-semibold transition-all cursor-pointer ${
                                chartType === "candles"
                                    ? "bg-white dark:bg-slate-700 text-indigo-600 dark:text-white shadow-xs"
                                    : "text-slate-500 hover:text-slate-900 dark:hover:text-slate-200"
                            }`}
                        >
                            Nến Nhật
                        </button>
                        <button
                            onClick={() => setChartType("area")}
                            className={`px-2.5 py-1 rounded-md font-semibold transition-all cursor-pointer ${
                                chartType === "area"
                                    ? "bg-white dark:bg-slate-700 text-indigo-600 dark:text-white shadow-xs"
                                    : "text-slate-500 hover:text-slate-900 dark:hover:text-slate-200"
                            }`}
                        >
                            Đường giá
                        </button>
                    </div>
                </div>

                {/* Right: Indicators & Timeframes */}
                <div className="flex flex-wrap items-center gap-2">
                    {/* Indicator Toggles */}
                    <div className="flex items-center gap-1 bg-slate-100 dark:bg-slate-800/80 p-1 rounded-xl border border-slate-200/60 dark:border-slate-800 text-[11px] font-semibold">
                        <button
                            onClick={() => setShowMA10((v) => !v)}
                            className={`px-2 py-0.5 rounded-md transition-all cursor-pointer flex items-center gap-1 ${
                                showMA10
                                    ? "bg-indigo-500/15 text-indigo-600 dark:text-indigo-400 font-bold border border-indigo-500/30"
                                    : "text-slate-400 hover:text-slate-600 line-through opacity-50"
                            }`}
                            title="MA10: Đường trung bình 10 phiên (ngắn hạn)"
                        >
                            <span className="w-2 h-2 rounded-full bg-[#818cf8]" />
                            <span>MA10</span>
                        </button>

                        <button
                            onClick={() => setShowMA50((v) => !v)}
                            className={`px-2 py-0.5 rounded-md transition-all cursor-pointer flex items-center gap-1 ${
                                showMA50
                                    ? "bg-sky-500/15 text-sky-600 dark:text-sky-400 font-bold border border-sky-500/30"
                                    : "text-slate-400 hover:text-slate-600 line-through opacity-50"
                            }`}
                            title="MA50: Đường trung bình 50 phiên (trung hạn)"
                        >
                            <span className="w-2 h-2 rounded-full bg-[#38bdf8]" />
                            <span>MA50</span>
                        </button>

                        <button
                            onClick={() => setShowMA200((v) => !v)}
                            className={`px-2 py-0.5 rounded-md transition-all cursor-pointer flex items-center gap-1 ${
                                showMA200
                                    ? "bg-orange-500/15 text-orange-600 dark:text-orange-400 font-bold border border-orange-500/30"
                                    : "text-slate-400 hover:text-slate-600 line-through opacity-50"
                            }`}
                            title="MA200: Đường trung bình 200 phiên (dài hạn)"
                        >
                            <span className="w-2 h-2 rounded-full bg-[#f97316]" />
                            <span>MA200</span>
                        </button>

                        <button
                            onClick={() => setShowVolume((v) => !v)}
                            className={`px-2 py-0.5 rounded-md transition-all cursor-pointer flex items-center gap-1 ${
                                showVolume
                                    ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 font-bold border border-emerald-500/30"
                                    : "text-slate-400 hover:text-slate-600 line-through opacity-50"
                            }`}
                            title="Khối lượng giao dịch"
                        >
                            <span>Khối lượng</span>
                        </button>
                    </div>

                    {/* Timeframes */}
                    <div className="flex items-center gap-1 text-xs">
                        {(["1M", "3M", "6M", "1Y", "ALL"] as const).map((tf) => (
                            <button
                                key={tf}
                                onClick={() => setTimeframe(tf)}
                                className={`px-2.5 py-1 rounded-lg text-[11px] font-bold transition-all cursor-pointer ${
                                    timeframe === tf
                                        ? "bg-indigo-600 text-white shadow-xs"
                                        : "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700"
                                }`}
                            >
                                {tf === "1M" ? "1T" : tf === "3M" ? "3T" : tf === "6M" ? "6T" : tf === "1Y" ? "1N" : "Tất cả"}
                            </button>
                        ))}

                        <button
                            onClick={handleResetZoom}
                            className="p-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-500 hover:text-indigo-600 dark:hover:text-indigo-400 transition cursor-pointer"
                            title="Đặt lại góc nhìn tối ưu"
                        >
                            <RotateCcw size={13} />
                        </button>
                    </div>
                </div>
            </div>

            {/* 2. DYNAMIC OHLCV & INDICATOR LEGEND BAR (Interactive on Hover) */}
            <div className="px-4 py-2 bg-slate-900/95 dark:bg-slate-950/95 text-slate-200 border-b border-slate-800 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs font-mono select-none">
                {/* Date */}
                <div className="flex items-center gap-1.5 text-slate-400">
                    <Calendar size={13} className="text-slate-500" />
                    <span>{activeDisplay?.time || "--"}</span>
                </div>

                {/* OHLC Values */}
                <div className="flex items-center gap-3">
                    <div>
                        <span className="text-slate-400">Mở: </span>
                        <span className="font-bold text-white">{activeDisplay?.open?.toFixed(2) ?? "--"}</span>
                    </div>
                    <div>
                        <span className="text-slate-400">Cao: </span>
                        <span className="font-bold text-emerald-400">{activeDisplay?.high?.toFixed(2) ?? "--"}</span>
                    </div>
                    <div>
                        <span className="text-slate-400">Thấp: </span>
                        <span className="font-bold text-rose-400">{activeDisplay?.low?.toFixed(2) ?? "--"}</span>
                    </div>
                    <div>
                        <span className="text-slate-400">Đóng: </span>
                        <span className={`font-bold ${
                            (activeDisplay?.change ?? 0) > 0
                                ? "text-emerald-400"
                                : (activeDisplay?.change ?? 0) < 0
                                ? "text-rose-400"
                                : "text-amber-400"
                        }`}>
                            {activeDisplay?.close?.toFixed(2) ?? "--"}
                        </span>
                    </div>
                    <div>
                        <span className={`font-bold ${
                            (activeDisplay?.change ?? 0) > 0
                                ? "text-emerald-400"
                                : (activeDisplay?.change ?? 0) < 0
                                ? "text-rose-400"
                                : "text-slate-400"
                        }`}>
                            {(activeDisplay?.change ?? 0) > 0 ? "+" : ""}
                            {activeDisplay?.change?.toFixed(2)} ({(activeDisplay?.percent ?? 0) > 0 ? "+" : ""}{activeDisplay?.percent?.toFixed(2)}%)
                        </span>
                    </div>
                    {showVolume && (
                        <div>
                            <span className="text-slate-400">KL: </span>
                            <span className="font-bold text-sky-400">{formatVolume(activeDisplay?.volume ?? 0)}</span>
                        </div>
                    )}
                </div>

                {/* MA Values */}
                <div className="flex items-center gap-3 ml-auto border-l border-slate-800 pl-3">
                    {showMA10 && activeDisplay?.ma10 && (
                        <div className="flex items-center gap-1 text-[#818cf8]">
                            <span className="text-[10px] uppercase font-sans">MA10:</span>
                            <span className="font-bold">{activeDisplay.ma10.toFixed(2)}</span>
                        </div>
                    )}
                    {showMA50 && activeDisplay?.ma50 && (
                        <div className="flex items-center gap-1 text-[#38bdf8]">
                            <span className="text-[10px] uppercase font-sans">MA50:</span>
                            <span className="font-bold">{activeDisplay.ma50.toFixed(2)}</span>
                        </div>
                    )}
                    {showMA200 && activeDisplay?.ma200 && (
                        <div className="flex items-center gap-1 text-[#f97316]">
                            <span className="text-[10px] uppercase font-sans">MA200:</span>
                            <span className="font-bold">{activeDisplay.ma200.toFixed(2)}</span>
                        </div>
                    )}
                </div>
            </div>

            {/* 3. MAIN WORKSPACE: SIDE DRAWING TOOLBAR + CHART CANVAS */}
            <div className="relative flex w-full" style={{ height: `${height}px` }}>
                {/* SIDE DRAWING & MEASURING TOOLBAR (Custom Built) */}
                {showDrawingTools && (
                    <div className="w-12 border-r border-slate-200/80 dark:border-slate-800 bg-slate-50/80 dark:bg-slate-900/90 flex flex-col items-center py-3 gap-2 shrink-0 select-none z-10">
                        {/* Con trỏ Crosshair */}
                        <button
                            onClick={() => setActiveTool("cursor")}
                            className={`p-2 rounded-xl transition-all cursor-pointer ${
                                activeTool === "cursor"
                                    ? "bg-indigo-600 text-white shadow-md shadow-indigo-500/20"
                                    : "text-slate-500 dark:text-slate-400 hover:bg-slate-200/70 dark:hover:bg-slate-800"
                            }`}
                            title="Con trỏ định vị toạ độ"
                        >
                            <Crosshair size={17} />
                        </button>

                        {/* Thước đo biên độ giá (%) */}
                        <button
                            onClick={() => {
                                setActiveTool("measure");
                                setMeasurePoints([]);
                                setMeasureResult(null);
                            }}
                            className={`p-2 rounded-xl transition-all cursor-pointer relative ${
                                activeTool === "measure"
                                    ? "bg-indigo-600 text-white shadow-md shadow-indigo-500/20"
                                    : "text-slate-500 dark:text-slate-400 hover:bg-slate-200/70 dark:hover:bg-slate-800"
                            }`}
                            title="Thước đo biên độ giá & % (Nhấp 2 điểm trên biểu đồ để đo)"
                        >
                            <Ruler size={17} />
                            {activeTool === "measure" && (
                                <span className="absolute -top-1 -right-1 w-2 h-2 bg-emerald-500 rounded-full animate-ping" />
                            )}
                        </button>

                        {/* Đường cản / Hỗ trợ ngang */}
                        <button
                            onClick={() => setActiveTool("horizontal")}
                            className={`p-2 rounded-xl transition-all cursor-pointer ${
                                activeTool === "horizontal"
                                    ? "bg-indigo-600 text-white shadow-md shadow-indigo-500/20"
                                    : "text-slate-500 dark:text-slate-400 hover:bg-slate-200/70 dark:hover:bg-slate-800"
                            }`}
                            title="Vẽ đường cản ngang / Hỗ trợ (Nhấp vào mức giá trên nến để kẻ)"
                        >
                            <Minus size={17} />
                        </button>

                        <div className="w-6 h-[1px] bg-slate-200 dark:bg-slate-800 my-1" />

                        {/* Xóa nét vẽ */}
                        <button
                            onClick={handleClearDrawings}
                            className="p-2 rounded-xl text-slate-400 hover:text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950/30 transition-all cursor-pointer"
                            title="Xóa tất cả đường vẽ & thước đo"
                        >
                            <Trash2 size={17} />
                        </button>
                    </div>
                )}

                {/* CHART CANVAS */}
                <div className="flex-1 h-full relative bg-slate-950/20 overflow-hidden">
                    <div
                        ref={containerRef}
                        className="w-full h-full"
                    />

                    {/* IN-PLACE SKELETON / LOADING OVERLAY */}
                    {(!candleData || candleData.length === 0 || loading) && (
                        <div className="absolute inset-0 bg-slate-900/90 dark:bg-slate-950/90 backdrop-blur-xs flex flex-col items-center justify-center gap-3 z-30 pointer-events-none">
                            <div className="relative">
                                <div className="w-11 h-11 rounded-2xl bg-indigo-600/20 border border-indigo-500/40 flex items-center justify-center text-indigo-400">
                                    <TrendingUp size={22} className="animate-pulse" />
                                </div>
                                <span className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-indigo-500 rounded-full animate-ping" />
                            </div>
                            <span className="text-xs font-semibold text-slate-300">
                                Đang nạp dữ liệu nến & chỉ báo cho mã <span className="text-indigo-400 font-bold">{stock}</span>...
                            </span>
                        </div>
                    )}

                    {/* MEASUREMENT POPUP / OVERLAY */}
                    {activeTool === "measure" && measurePoints.length === 1 && (
                        <div className="absolute top-4 left-4 bg-indigo-600 text-white text-xs px-3 py-1.5 rounded-xl shadow-lg animate-pulse flex items-center gap-2 pointer-events-none z-20">
                            <Ruler size={14} />
                            <span>Đã chọn Điểm 1 ({measurePoints[0].price.toFixed(2)}). Nhấp điểm thứ 2 trên biểu đồ để đo!</span>
                        </div>
                    )}

                    {measureResult && (
                        <div className="absolute top-4 left-4 bg-slate-900/95 border border-indigo-500/40 text-white text-xs p-3 rounded-2xl shadow-xl space-y-1.5 z-20 backdrop-blur-md">
                            <div className="flex items-center justify-between gap-4 border-b border-slate-800 pb-1.5">
                                <span className="font-bold text-indigo-400 flex items-center gap-1">
                                    <Ruler size={13} /> Kết quả đo lường:
                                </span>
                                <button
                                    onClick={() => setMeasureResult(null)}
                                    className="text-slate-400 hover:text-white cursor-pointer"
                                >
                                    ✕
                                </button>
                            </div>
                            <div className="grid grid-cols-2 gap-x-4 gap-y-1 font-mono text-[11px]">
                                <div>Từ giá: <span className="font-bold text-slate-200">{measureResult.startPrice.toFixed(2)}</span></div>
                                <div>Đến giá: <span className="font-bold text-slate-200">{measureResult.endPrice.toFixed(2)}</span></div>
                                <div>Chênh lệch: <span className={`font-bold ${measureResult.priceDiff >= 0 ? "text-emerald-400" : "text-rose-400"}`}>{measureResult.priceDiff > 0 ? "+" : ""}{measureResult.priceDiff.toFixed(2)}</span></div>
                                <div>Biên độ: <span className={`font-bold ${measureResult.percentDiff >= 0 ? "text-emerald-400" : "text-rose-400"}`}>{measureResult.percentDiff > 0 ? "+" : ""}{measureResult.percentDiff.toFixed(2)}%</span></div>
                                <div className="col-span-2 text-slate-400 text-[10px]">Khoảng cách: {measureResult.bars} phiên giao dịch ({measureResult.startTime} ➔ {measureResult.endTime})</div>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
