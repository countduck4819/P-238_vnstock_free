"use client";

import { useEffect, useState, useMemo } from "react";
import Image from "next/image";
import {
    AlertCircle,
    ImageIcon,
    Loader2,
    RefreshCw,
    Telescope,
    TrendingUp,
    TrendingDown,
    Sparkles,
    Calendar,
    Target,
    Activity,
    Bot,
    Maximize2,
    BarChart3,
    ArrowUpRight,
    ArrowDownRight,
} from "lucide-react";
import { api } from "@/utils/axiosInstance";
import { formatPrice } from "@/lib/utils";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { useAppDispatch, useAppSelector } from "@/redux/hooks";
import { fetchStockPredictionQuery } from "@/store/stock-prediction/stock-prediction.api";

type ForecastPoint = {
    date?: string;
    predicted_close?: number;
};

type V6Prediction = {
    symbol: string;
    date: string;
    long_term_rank: number;
    long_term_trend_probability: number | null;
    price_forecast?: {
        last_close_price: number;
        predicted_price: number;
        forecast_horizon_sessions: number;
        forecast: ForecastPoint[];
        as_of_date: string;
        chart_path?: string | null;
    } | null;
};

type V6Payload = {
    trend_type: "long_term";
    as_of_date: string;
    snapshot_date: string;
    trade_authorized: false;
    advisory: {
        fixed_horizon_sessions: null;
        advisory_only: true;
        not_a_trade_instruction: true;
        independent_from_h120: true;
    };
    summary: { eligible_rows?: number; shortlist_rows?: number };
    predictions: V6Prediction[];
};

type StockPredictionRow = {
    ticker: string;
    lastClosePrice: number;
    predictedPrice: number;
    pEnsemble?: number | null;
    chartPath?: string | null;
    predictedOn: string;
};

function resolveV6Payload(responseBody: unknown): V6Payload | null {
    const body = responseBody as Record<string, any> | null;
    const candidates = [body?.data?.data, body?.data, body];

    for (const candidate of candidates) {
        if (
            (candidate?.trend_type === undefined ||
                candidate?.trend_type === "long_term") &&
            candidate?.trade_authorized === false &&
            candidate?.advisory?.independent_from_h120 === true &&
            Array.isArray(candidate?.predictions)
        ) {
            return {
                ...candidate,
                trend_type: "long_term",
            } as V6Payload;
        }
    }

    return null;
}

function mergeStockPredictionData(
    payload: V6Payload,
    stockRows: StockPredictionRow[],
): V6Payload {
    const rowsByTicker = new Map(
        stockRows.map((row) => [row.ticker.trim().toUpperCase(), row]),
    );
    const latestPredictionDate = stockRows.reduce<string | null>(
        (latest, row) => {
            const currentTime = new Date(row.predictedOn).getTime();
            const latestTime = latest ? new Date(latest).getTime() : 0;
            return Number.isFinite(currentTime) && currentTime > latestTime
                ? row.predictedOn
                : latest;
        },
        null,
    );

    return {
        ...payload,
        as_of_date: latestPredictionDate ?? payload.as_of_date,
        predictions: payload.predictions.map((prediction) => {
            const stockRow = rowsByTicker.get(
                prediction.symbol.trim().toUpperCase(),
            );
            if (!stockRow) return prediction;

            const lastClosePrice = Number(stockRow.lastClosePrice);
            const predictedPrice = Number(stockRow.predictedPrice);
            const pEnsemble =
                stockRow.pEnsemble == null ? null : Number(stockRow.pEnsemble);
            const existingForecast = prediction.price_forecast;
            const hasPrices =
                Number.isFinite(lastClosePrice) &&
                Number.isFinite(predictedPrice);

            return {
                ...prediction,
                date: stockRow.predictedOn || prediction.date,
                long_term_trend_probability:
                    typeof pEnsemble === "number" && Number.isFinite(pEnsemble)
                        ? pEnsemble
                        : prediction.long_term_trend_probability,
                price_forecast: hasPrices
                    ? {
                          last_close_price: lastClosePrice,
                          predicted_price: predictedPrice,
                          forecast_horizon_sessions:
                              existingForecast?.forecast_horizon_sessions || 78,
                          forecast: existingForecast?.forecast ?? [],
                          as_of_date:
                              stockRow.predictedOn ||
                              existingForecast?.as_of_date ||
                              prediction.date,
                          chart_path:
                              stockRow.chartPath ??
                              existingForecast?.chart_path ??
                              null,
                      }
                    : existingForecast,
            };
        }),
    };
}

const percentage = new Intl.NumberFormat("vi-VN", {
    style: "percent",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
});
const dateFormatter = new Intl.DateTimeFormat("vi-VN", { dateStyle: "medium" });

function displayDate(value?: string) {
    if (!value) return "--";
    const date = new Date(`${value.slice(0, 10)}T00:00:00`);
    return Number.isNaN(date.getTime()) ? value : dateFormatter.format(date);
}

// Interactive SVG Forecast Curve Component
function InteractiveForecastVisual({
    prediction,
}: {
    prediction: V6Prediction;
}) {
    const [hoveredPoint, setHoveredPoint] = useState<{
        index: number;
        date: string;
        price: number;
        diffPercent: number;
        x: number;
        y: number;
    } | null>(null);

    const forecast = prediction.price_forecast?.forecast || [];
    const lastClose = Number(prediction.price_forecast?.last_close_price) || 0;
    const targetPrice = Number(prediction.price_forecast?.predicted_price) || 0;
    const horizonSessions =
        Number(prediction.price_forecast?.forecast_horizon_sessions) || 78;

    const dataPoints = useMemo(() => {
        let rawPoints = forecast;

        // Nếu chuỗi dự báo chi tiết chưa có sẵn từ model nhưng có mức giá mục tiêu và giá tham chiếu
        if (
            (!rawPoints || rawPoints.length === 0) &&
            lastClose > 0 &&
            targetPrice > 0
        ) {
            const steps = Math.max(5, Math.min(horizonSessions || 10, 15));
            const synthetic: ForecastPoint[] = [];
            const baseDate = new Date(
                prediction.price_forecast?.as_of_date ||
                    prediction.date ||
                    Date.now(),
            );

            for (let i = 1; i <= steps; i++) {
                const date = new Date(baseDate);
                date.setDate(date.getDate() + Math.round(i * 1.4));
                const progress = i / steps;
                const curveFactor = (1 - Math.cos(progress * Math.PI)) / 2;
                const simulatedPrice =
                    lastClose + (targetPrice - lastClose) * curveFactor;

                synthetic.push({
                    date: date.toISOString().slice(0, 10),
                    predicted_close: Number(simulatedPrice.toFixed(2)),
                });
            }
            rawPoints = synthetic;
        }

        if (!rawPoints.length) return [];
        return rawPoints
            .map((item, idx) => {
                const price = Number(item.predicted_close);
                if (Number.isNaN(price) || price <= 0) return null;
                const diffPercent =
                    lastClose > 0 ? ((price - lastClose) / lastClose) * 100 : 0;
                return {
                    index: idx,
                    sessionLabel: `T+${idx + 1}`,
                    date: item.date
                        ? item.date.slice(0, 10)
                        : `Phiên T+${idx + 1}`,
                    price,
                    diffPercent,
                };
            })
            .filter(Boolean) as Array<{
            index: number;
            sessionLabel: string;
            date: string;
            price: number;
            diffPercent: number;
        }>;
    }, [forecast, lastClose, targetPrice, horizonSessions, prediction]);

    if (!dataPoints.length) {
        return (
            <div className="flex h-64 items-center justify-center text-xs text-slate-400">
                Đang cập nhật chuỗi dữ liệu dự báo cho mã {prediction.symbol}.
            </div>
        );
    }

    const allPrices = [lastClose, ...dataPoints.map((d) => d.price)].filter(
        (p) => p > 0,
    );
    const minPrice = Math.min(...allPrices) * 0.985;
    const maxPrice = Math.max(...allPrices) * 1.015;
    const priceRange = maxPrice - minPrice || 1;

    // SVG coordinate space
    const width = 1100;
    const height = 350;
    const paddingLeft = 70;
    const paddingRight = 40;
    const paddingTop = 30;
    const paddingBottom = 40;

    const chartW = width - paddingLeft - paddingRight;
    const chartH = height - paddingTop - paddingBottom;

    const getY = (price: number) => {
        const norm = (price - minPrice) / priceRange;
        return paddingTop + chartH - norm * chartH;
    };

    const getX = (index: number) => {
        if (dataPoints.length === 1) return paddingLeft + chartW / 2;
        return paddingLeft + (index / (dataPoints.length - 1)) * chartW;
    };

    const lastCloseY = getY(lastClose);

    // Build curve path
    const pointsCoords = dataPoints.map((pt, i) => ({
        x: getX(i),
        y: getY(pt.price),
        ...pt,
    }));

    const pathD = pointsCoords.reduce((acc, pt, i, arr) => {
        if (i === 0) return `M ${pt.x} ${pt.y}`;
        const prev = arr[i - 1];
        const cpX1 = prev.x + (pt.x - prev.x) / 2;
        const cpY1 = prev.y;
        const cpX2 = prev.x + (pt.x - prev.x) / 2;
        const cpY2 = pt.y;
        return `${acc} C ${cpX1} ${cpY1}, ${cpX2} ${cpY2}, ${pt.x} ${pt.y}`;
    }, "");

    const areaD = `${pathD} L ${pointsCoords[pointsCoords.length - 1].x} ${
        paddingTop + chartH
    } L ${pointsCoords[0].x} ${paddingTop + chartH} Z`;

    const isOverallUp =
        (prediction.price_forecast?.predicted_price || 0) >= lastClose;

    const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
        const svg = e.currentTarget;
        const rect = svg.getBoundingClientRect();
        if (!rect.width || !pointsCoords.length) return;
        const mouseX = ((e.clientX - rect.left) / rect.width) * width;

        if (mouseX < paddingLeft - 25 || mouseX > width - paddingRight + 25) {
            setHoveredPoint((prev) => (prev === null ? prev : null));
            return;
        }

        let closest = pointsCoords[0];
        let minDist = Math.abs(mouseX - closest.x);

        for (let i = 1; i < pointsCoords.length; i++) {
            const dist = Math.abs(mouseX - pointsCoords[i].x);
            if (dist < minDist) {
                minDist = dist;
                closest = pointsCoords[i];
            }
        }

        setHoveredPoint((prev) => {
            if (prev?.index === closest.index) return prev;
            return {
                index: closest.index,
                date: closest.date,
                price: closest.price,
                diffPercent: closest.diffPercent,
                x: closest.x,
                y: closest.y,
            };
        });
    };

    return (
        <div className="relative w-full select-none">
            {/* Top Interactive HUD Info Bar */}
            <div className="absolute top-2 left-3 sm:left-4 z-10 pointer-events-none flex items-center gap-2 text-xs">
                {hoveredPoint ? (
                    <div className="flex items-center gap-2 sm:gap-3 px-3 py-1.5 rounded-xl bg-slate-950/95 border border-blue-500/50 shadow-xl backdrop-blur-md">
                        <span className="font-bold text-blue-400 font-mono text-[11px] sm:text-xs">
                            Phiên T+{hoveredPoint.index + 1} (
                            {hoveredPoint.date})
                        </span>
                        <span className="text-slate-600 font-bold">•</span>
                        <span className="font-mono font-black text-white text-xs sm:text-sm">
                            {hoveredPoint.price < 1000
                                ? Math.round(
                                      hoveredPoint.price * 1000,
                                  ).toLocaleString("vi-VN")
                                : Math.round(hoveredPoint.price).toLocaleString(
                                      "vi-VN",
                                  )}{" "}
                            VNĐ
                        </span>
                        <span
                            className={`font-mono font-bold text-[10px] sm:text-[11px] px-1.5 py-0.5 rounded ${
                                hoveredPoint.diffPercent >= 0
                                    ? "bg-emerald-500/20 text-emerald-400"
                                    : "bg-rose-500/20 text-rose-400"
                            }`}
                        >
                            {hoveredPoint.diffPercent >= 0 ? "+" : ""}
                            {hoveredPoint.diffPercent.toFixed(2)}%
                        </span>
                    </div>
                ) : (
                    <div className="text-[11px] text-slate-400 font-medium px-2.5 py-1 rounded-lg bg-slate-900/80 border border-slate-800 backdrop-blur-xs">
                        ⚡ Rê chuột dọc theo biểu đồ để xem chi tiết từng phiên
                    </div>
                )}
            </div>

            <svg
                viewBox={`0 0 ${width} ${height}`}
                className="w-full h-auto overflow-visible cursor-crosshair"
                onMouseMove={handleMouseMove}
                onMouseLeave={() => setHoveredPoint(null)}
            >
                <defs>
                    <linearGradient
                        id="forecastAreaGrad"
                        x1="0%"
                        y1="0%"
                        x2="0%"
                        y2="100%"
                    >
                        <stop
                            offset="0%"
                            stopColor={isOverallUp ? "#3b82f6" : "#f43f5e"}
                            stopOpacity="0.35"
                        />
                        <stop
                            offset="70%"
                            stopColor={isOverallUp ? "#8b5cf6" : "#f43f5e"}
                            stopOpacity="0.08"
                        />
                        <stop
                            offset="100%"
                            stopColor="#000000"
                            stopOpacity="0"
                        />
                    </linearGradient>

                    <linearGradient
                        id="forecastLineGrad"
                        x1="0%"
                        y1="0%"
                        x2="100%"
                        y2="0%"
                    >
                        <stop offset="0%" stopColor="#38bdf8" />
                        <stop offset="50%" stopColor="#6366f1" />
                        <stop
                            offset="100%"
                            stopColor={isOverallUp ? "#10b981" : "#f43f5e"}
                        />
                    </linearGradient>

                    <filter
                        id="glowForecast"
                        x="-20%"
                        y="-20%"
                        width="140%"
                        height="140%"
                    >
                        <feGaussianBlur stdDeviation="3" result="blur" />
                        <feComposite
                            in="SourceGraphic"
                            in2="blur"
                            operator="over"
                        />
                    </filter>
                </defs>

                {/* Horizontal Grid lines */}
                {[0, 0.25, 0.5, 0.75, 1].map((pct) => {
                    const priceVal = minPrice + pct * priceRange;
                    const y = paddingTop + chartH - pct * chartH;
                    return (
                        <g key={pct} className="pointer-events-none">
                            <line
                                x1={paddingLeft}
                                y1={y}
                                x2={width - paddingRight}
                                y2={y}
                                stroke="currentColor"
                                strokeDasharray="3 4"
                                className="text-slate-200 dark:text-slate-800"
                                strokeWidth="1"
                            />
                            <text
                                x={paddingLeft - 10}
                                y={y + 4}
                                textAnchor="end"
                                className="fill-slate-400 text-[10px] font-mono font-medium"
                            >
                                {priceVal < 1000
                                    ? Math.round(
                                          priceVal * 1000,
                                      ).toLocaleString("vi-VN")
                                    : Math.round(priceVal).toLocaleString(
                                          "vi-VN",
                                      )}
                            </text>
                        </g>
                    );
                })}

                {/* Baseline: Last Close Price */}
                {lastClose > 0 && (
                    <g className="pointer-events-none">
                        <line
                            x1={paddingLeft}
                            y1={lastCloseY}
                            x2={width - paddingRight}
                            y2={lastCloseY}
                            stroke="#94a3b8"
                            strokeDasharray="4 4"
                            strokeWidth="1.5"
                            className="opacity-70"
                        />
                        <rect
                            x={width - paddingRight - 122}
                            y={lastCloseY - 17}
                            width={122}
                            height={15}
                            rx={4}
                            fill="#0f172a"
                            fillOpacity="0.85"
                            stroke="#334155"
                            strokeWidth="0.5"
                        />
                        <text
                            x={width - paddingRight - 6}
                            y={lastCloseY - 6}
                            textAnchor="end"
                            className="fill-slate-300 dark:fill-slate-400 text-[9px] font-bold uppercase font-mono tracking-wide"
                        >
                            Tham chiếu:{" "}
                            {lastClose < 1000
                                ? Math.round(lastClose * 1000).toLocaleString(
                                      "vi-VN",
                                  )
                                : Math.round(lastClose).toLocaleString("vi-VN")}
                        </text>
                    </g>
                )}

                {/* Gradient Area under curve */}
                <path
                    d={areaD}
                    fill="url(#forecastAreaGrad)"
                    className="pointer-events-none"
                />

                {/* Main Prediction Trend Line */}
                <path
                    d={pathD}
                    fill="none"
                    stroke="url(#forecastLineGrad)"
                    strokeWidth="3.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    filter="url(#glowForecast)"
                    className="pointer-events-none"
                />

                {/* Vertical Guideline on Hover */}
                {hoveredPoint && (
                    <line
                        x1={hoveredPoint.x}
                        y1={paddingTop}
                        x2={hoveredPoint.x}
                        y2={paddingTop + chartH}
                        stroke="#60a5fa"
                        strokeDasharray="3 3"
                        strokeWidth="1.5"
                        className="opacity-75 pointer-events-none"
                    />
                )}

                {/* Static Points & Labels on curve */}
                {pointsCoords.map((pt) => {
                    const isHovered = hoveredPoint?.index === pt.index;
                    return (
                        <g key={pt.index} className="pointer-events-none">
                            {/* Node Dot */}
                            <circle
                                cx={pt.x}
                                cy={pt.y}
                                r={isHovered ? 5.5 : 3.5}
                                fill={isHovered ? "#ffffff" : "#6366f1"}
                                stroke={isHovered ? "#3b82f6" : "#ffffff"}
                                strokeWidth={isHovered ? 2 : 1}
                            />

                            {/* X-axis Session label */}
                            {(pt.index === 0 ||
                                pt.index ===
                                    Math.floor(pointsCoords.length / 2) ||
                                pt.index === pointsCoords.length - 1 ||
                                isHovered) && (
                                <text
                                    x={pt.x}
                                    y={paddingTop + chartH + 20}
                                    textAnchor="middle"
                                    className={`text-[10px] font-mono ${
                                        isHovered
                                            ? "fill-blue-400 font-bold"
                                            : "fill-slate-500 dark:fill-slate-400"
                                    }`}
                                >
                                    {pt.date}
                                </text>
                            )}
                        </g>
                    );
                })}

                {/* Hover Highlight Ring */}
                {hoveredPoint && (
                    <g className="pointer-events-none">
                        <circle
                            cx={hoveredPoint.x}
                            cy={hoveredPoint.y}
                            r={10}
                            fill={
                                hoveredPoint.diffPercent >= 0
                                    ? "#10b981"
                                    : "#f43f5e"
                            }
                            fillOpacity="0.25"
                            stroke={
                                hoveredPoint.diffPercent >= 0
                                    ? "#10b981"
                                    : "#f43f5e"
                            }
                            strokeWidth={1.5}
                        />
                        <circle
                            cx={hoveredPoint.x}
                            cy={hoveredPoint.y}
                            r={5.5}
                            fill="#ffffff"
                            stroke="#3b82f6"
                            strokeWidth="2.5"
                        />
                    </g>
                )}

                {/* Dedicated Transparent Mouse Capture Plane */}
                <rect
                    x={0}
                    y={0}
                    width={width}
                    height={height}
                    fill="transparent"
                    className="cursor-crosshair"
                />
            </svg>
        </div>
    );
}

export default function V6LongTermAdvisory() {
    const dispatch = useAppDispatch();
    const stockPredictionList = useAppSelector(
        (state) => state.stockPrediction.list,
    ) as StockPredictionRow[];
    const [payload, setPayload] = useState<V6Payload | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [preview, setPreview] = useState<V6Prediction | null>(null);
    const [viewMode, setViewMode] = useState<"interactive" | "technical">(
        "interactive",
    );

    const load = async () => {
        setLoading(true);
        setError(null);
        try {
            const [response, stockPredictionResponse] = await Promise.all([
                api.get("/wave-v6/latest", {
                    params: { limit: 50 },
                }),
                dispatch(
                    fetchStockPredictionQuery({ page: 1, limit: 50 }),
                ).unwrap(),
            ]);
            const data = resolveV6Payload(response.data);
            if (!data) {
                throw new Error("Dữ liệu xu hướng dài hạn không hợp lệ.");
            }
            const stockRows = Array.isArray(stockPredictionResponse?.data)
                ? (stockPredictionResponse.data as StockPredictionRow[])
                : stockPredictionList;
            setPayload(mergeStockPredictionData(data, stockRows));
        } catch {
            setPayload(null);
            setError(
                "Chưa thể tải gợi ý xu hướng dài hạn. Vui lòng thử lại sau.",
            );
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        void load();
    }, []);

    const handleAskAI = (symbol: string) => {
        window.dispatchEvent(
            new CustomEvent("open-ai-chat", {
                detail: {
                    prompt: `Hãy phân tích chi tiết triển vọng xu hướng và dự báo giá của mã ${symbol} theo mô hình kết hợp LSTM và XGBoost. Điểm mua/bán và rủi ro cần lưu ý là gì?`,
                },
            }),
        );
    };

    // Calculate metrics for selected preview
    const previewMetrics = useMemo(() => {
        if (!preview?.price_forecast) return null;
        const lastClose = Number(preview.price_forecast.last_close_price) || 0;
        const targetPrice = Number(preview.price_forecast.predicted_price) || 0;
        const diffPercent =
            lastClose > 0 ? ((targetPrice - lastClose) / lastClose) * 100 : 0;
        const isUp = diffPercent >= 0;
        return {
            lastClose,
            targetPrice,
            diffPercent,
            isUp,
            sessions: preview.price_forecast.forecast_horizon_sessions || 78,
            forecast: preview.price_forecast.forecast || [],
        };
    }, [preview]);

    return (
        <div className="space-y-4">
            <div className="rounded-xl border border-blue-200 bg-blue-50/90 px-4 py-3 text-xs leading-5 text-blue-900 shadow-xs dark:border-blue-900/70 dark:bg-blue-950/40 dark:text-blue-200">
                <div className="flex items-start gap-2.5">
                    <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-blue-600 dark:text-blue-400" />
                    <div>
                        <span className="font-bold">
                            Mô hình AI Đa tầng (XGBoost Wave V6 + LSTM Deep
                            Learning):{" "}
                        </span>
                        Xếp hạng tiềm năng hình thành xu hướng dài hạn và dự báo
                        quỹ đạo giá trong các phiên tiếp theo. Kết quả mang tính
                        chất tham khảo chiến lược, không phải khuyến nghị đầu tư
                        tự động.
                    </div>
                </div>
            </div>

            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                    <h3 className="flex items-center gap-2 text-base font-bold text-slate-900 dark:text-white">
                        <Telescope className="h-5 w-5 text-blue-600 dark:text-blue-400" />
                        Xu hướng dài hạn + Dự đoán giá AI
                    </h3>
                    {payload && (
                        <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                            Phiên dữ liệu tổng hợp:{" "}
                            <span className="font-semibold text-slate-700 dark:text-slate-300">
                                {displayDate(payload.as_of_date)}
                            </span>
                        </p>
                    )}
                </div>
                <button
                    type="button"
                    onClick={() => void load()}
                    disabled={loading}
                    className="inline-flex h-9 items-center justify-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3.5 text-xs font-semibold text-slate-700 shadow-xs transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
                >
                    <RefreshCw
                        className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`}
                    />
                    Làm mới
                </button>
            </div>

            {loading && (
                <div className="flex min-h-48 items-center justify-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                    <Loader2 className="h-5 w-5 animate-spin text-blue-600" />
                    Đang tải danh mục dự báo AI…
                </div>
            )}
            {!loading && error && (
                <div className="rounded-xl border border-dashed border-slate-300 px-4 py-8 text-center text-xs text-slate-500 dark:border-slate-700 dark:text-slate-400">
                    {error}
                </div>
            )}
            {!loading && payload && (
                <>
                    <div className="grid grid-cols-2 gap-3 sm:max-w-md">
                        <div className="rounded-xl border border-slate-200/80 bg-slate-50/80 px-3.5 py-2.5 dark:border-slate-800 dark:bg-slate-800/70">
                            <p className="text-[11px] font-medium text-slate-500 dark:text-slate-400">
                                Mã được AI xếp hạng
                            </p>
                            <p className="mt-0.5 text-base font-bold text-slate-900 dark:text-white">
                                {payload.summary?.eligible_rows ?? "--"}{" "}
                                <span className="text-xs font-normal text-slate-400">
                                    mã
                                </span>
                            </p>
                        </div>
                        <div className="rounded-xl border border-slate-200/80 bg-slate-50/80 px-3.5 py-2.5 dark:border-slate-800 dark:bg-slate-800/70">
                            <p className="text-[11px] font-medium text-slate-500 dark:text-slate-400">
                                Top mã tiềm năng
                            </p>
                            <p className="mt-0.5 text-base font-bold text-blue-600 dark:text-blue-400">
                                {payload.predictions.length}{" "}
                                <span className="text-xs font-normal text-slate-400">
                                    mã
                                </span>
                            </p>
                        </div>
                    </div>

                    <div className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
                        <div className="overflow-x-auto">
                            <table className="w-full min-w-[780px] border-collapse text-left text-xs">
                                <thead>
                                    <tr className="border-b border-slate-200/80 bg-slate-50/90 text-[11px] font-bold uppercase tracking-wider text-slate-600 dark:border-slate-800 dark:bg-slate-800/60 dark:text-slate-300">
                                        <th className="px-4 py-3.5 text-center">
                                            Hạng
                                        </th>
                                        <th className="px-4 py-3.5">Mã CP</th>
                                        <th className="px-4 py-3.5 text-center">
                                            Xác suất tăng
                                        </th>
                                        <th className="px-4 py-3.5 text-center">
                                            Biểu đồ dự báo AI
                                        </th>
                                        <th className="px-4 py-3.5 text-center">
                                            Giá dự báo mục tiêu
                                        </th>
                                        <th className="px-4 py-3.5 text-center">
                                            Phiên dữ liệu
                                        </th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                                    {payload.predictions.map((prediction) => (
                                        <tr
                                            key={prediction.symbol}
                                            className="transition-colors hover:bg-slate-50/70 dark:hover:bg-slate-800/50"
                                        >
                                            <td className="px-4 py-3.5 text-center font-mono font-bold text-slate-700 dark:text-slate-300">
                                                #{prediction.long_term_rank}
                                            </td>
                                            <td className="px-4 py-3.5">
                                                <div className="inline-flex items-center gap-2">
                                                    <span className="rounded-lg bg-blue-500/10 px-2.5 py-1 text-xs font-black tracking-wide text-blue-700 dark:text-blue-300 border border-blue-500/20">
                                                        {prediction.symbol}
                                                    </span>
                                                </div>
                                            </td>
                                            <td className="px-4 py-3.5 text-center">
                                                <span className="inline-flex rounded-full bg-indigo-500/10 px-2.5 py-1 font-mono font-bold text-indigo-700 dark:text-indigo-300">
                                                    {typeof prediction.long_term_trend_probability ===
                                                    "number"
                                                        ? percentage.format(
                                                              prediction.long_term_trend_probability,
                                                          )
                                                        : "--"}
                                                </span>
                                            </td>
                                            <td className="px-4 py-3.5 text-center">
                                                {prediction.price_forecast
                                                    ?.chart_path ? (
                                                    <button
                                                        type="button"
                                                        onClick={() => {
                                                            setPreview(
                                                                prediction,
                                                            );
                                                            setViewMode(
                                                                prediction
                                                                    .price_forecast
                                                                    ?.forecast
                                                                    ?.length
                                                                    ? "interactive"
                                                                    : "technical",
                                                            );
                                                        }}
                                                        className="group relative mx-auto flex items-center gap-2 h-14 w-36 overflow-hidden rounded-xl border border-slate-200 bg-slate-900/90 shadow-sm transition-all hover:border-blue-500 hover:shadow-md hover:scale-[1.03] focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-slate-700 cursor-pointer p-1"
                                                        aria-label={`Xem biểu đồ dự báo ${prediction.symbol}`}
                                                    >
                                                        <div className="relative w-full h-full rounded-lg overflow-hidden">
                                                            <Image
                                                                src={`/${prediction.price_forecast.chart_path.replace(/^\/+/, "")}`}
                                                                alt={`Biểu đồ dự báo ${prediction.symbol}`}
                                                                fill
                                                                sizes="144px"
                                                                unoptimized
                                                                className="object-cover opacity-80 group-hover:opacity-100 transition-opacity"
                                                            />
                                                            <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent flex items-end justify-center pb-0.5">
                                                                <span className="text-[10px] font-bold text-white flex items-center gap-1 drop-shadow-xs">
                                                                    <Maximize2
                                                                        size={
                                                                            10
                                                                        }
                                                                    />{" "}
                                                                    Phóng to
                                                                </span>
                                                            </div>
                                                        </div>
                                                    </button>
                                                ) : (
                                                    <span className="inline-flex items-center gap-1 text-slate-400">
                                                        <ImageIcon className="h-3.5 w-3.5" />{" "}
                                                        --
                                                    </span>
                                                )}
                                            </td>
                                            <td className="px-4 py-3.5 text-center">
                                                {prediction.price_forecast ? (
                                                    <div className="space-y-0.5">
                                                        <div className="font-mono font-bold text-slate-900 dark:text-white text-[13px]">
                                                            {formatPrice(
                                                                prediction
                                                                    .price_forecast
                                                                    .predicted_price,
                                                            )}
                                                        </div>
                                                        <div className="text-[10px] text-slate-500 dark:text-slate-400">
                                                            {`sau ${prediction.price_forecast.forecast_horizon_sessions || 78} phiên`}
                                                        </div>
                                                    </div>
                                                ) : (
                                                    <span className="text-slate-400">
                                                        --
                                                    </span>
                                                )}
                                            </td>
                                            <td className="px-4 py-3.5 text-center text-slate-500 dark:text-slate-400">
                                                {displayDate(prediction.date)}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </>
            )}

            {/* ========================================================================= */}
            {/* ENLARGED, HIGH-TECH & IMMERSIVE FORECAST MODAL DIALOG */}
            {/* ========================================================================= */}
            <Dialog
                modal={false}
                open={preview !== null}
                onOpenChange={(open) => !open && setPreview(null)}
            >
                <DialogContent
                    onPointerDownOutside={(e) => {
                        const target = e.target as HTMLElement | null;
                        if (
                            target &&
                            (target.closest(".ai-chat-window") ||
                                target.closest(".ai-chat-trigger"))
                        ) {
                            e.preventDefault();
                        }
                    }}
                    onInteractOutside={(e) => {
                        const target = e.target as HTMLElement | null;
                        if (
                            target &&
                            (target.closest(".ai-chat-window") ||
                                target.closest(".ai-chat-trigger"))
                        ) {
                            e.preventDefault();
                        }
                    }}
                    className="w-[95vw] max-w-5xl xl:max-w-6xl max-h-[90vh] overflow-y-auto border border-slate-200 bg-white p-0 shadow-2xl dark:border-slate-800 dark:bg-slate-950 rounded-2xl sm:rounded-3xl flex flex-col text-slate-900 dark:text-slate-100"
                >
                    {preview && previewMetrics && (
                        <>
                            {/* 1. MODAL HEADER BAR */}
                            <DialogHeader className="px-5 sm:px-6 py-3.5 sm:py-4 border-b border-slate-200/80 dark:border-slate-800/80 bg-slate-50/90 dark:bg-slate-900/90 backdrop-blur-md shrink-0 pr-12 sm:pr-14">
                                <div className="flex flex-wrap items-center justify-between gap-3">
                                    <div className="flex items-center gap-3">
                                        <div className="flex items-center justify-center w-11 h-11 rounded-2xl bg-gradient-to-br from-blue-600 via-indigo-600 to-purple-600 text-white font-black text-lg shadow-md shadow-indigo-500/20 shrink-0">
                                            {preview.symbol}
                                        </div>
                                        <div>
                                            <div className="flex items-center gap-2 flex-wrap">
                                                <DialogTitle className="text-base sm:text-lg font-extrabold text-slate-900 dark:text-white tracking-tight">
                                                    Biểu đồ Dự báo Giá & Xu
                                                    hướng AI
                                                </DialogTitle>
                                                <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-blue-500/10 text-blue-700 dark:text-blue-300 border border-blue-500/20">
                                                    Hạng #
                                                    {preview.long_term_rank}
                                                </span>
                                            </div>
                                            <DialogDescription className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                                                Mô hình LSTM Deep Learning &
                                                XGBoost Wave V6 • Phiên dữ liệu{" "}
                                                {displayDate(
                                                    payload?.as_of_date,
                                                )}
                                            </DialogDescription>
                                        </div>
                                    </div>

                                    {/* Action Button (Căn cách xa nút đóng X ở góc phải) */}
                                    <div className="flex items-center gap-2 mr-4 sm:mr-6">
                                        <button
                                            type="button"
                                            onClick={() =>
                                                handleAskAI(preview.symbol)
                                            }
                                            className="px-3.5 py-2 rounded-xl bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 hover:from-blue-500 hover:via-indigo-500 hover:to-purple-500 text-white font-bold text-xs shadow-md shadow-indigo-500/30 hover:scale-[1.02] active:scale-[0.98] transition-all flex items-center gap-1.5 cursor-pointer border border-white/20"
                                        >
                                            <Bot
                                                size={15}
                                                className="text-cyan-200 shrink-0"
                                            />
                                            <span className="tracking-wide">
                                                Hỏi AI về mã này
                                            </span>
                                            <span className="flex h-2 w-2 relative items-center justify-center shrink-0 ml-0.5">
                                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-80" />
                                                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-400" />
                                            </span>
                                        </button>
                                    </div>
                                </div>
                            </DialogHeader>

                            {/* 2. MODAL BODY */}
                            <div className="p-4 sm:p-5 space-y-4 sm:space-y-5 flex-1 overflow-y-auto">
                                {/* 3 STAT CARDS */}
                                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                                    {/* Card 1: Giá tham chiếu */}
                                    <div className="rounded-2xl border border-slate-200/80 bg-slate-50/70 dark:border-slate-800 dark:bg-slate-900/60 p-3.5 sm:p-4 min-w-0 flex flex-col justify-between overflow-hidden shadow-xs">
                                        <div className="flex items-center justify-between text-xs font-semibold text-slate-500 dark:text-slate-400">
                                            <span>Giá tham chiếu</span>
                                            <Activity
                                                size={14}
                                                className="text-slate-400 shrink-0"
                                            />
                                        </div>
                                        <div className="mt-2 flex items-baseline gap-1.5 font-mono">
                                            <span className="text-xl sm:text-2xl font-black text-slate-900 dark:text-white truncate">
                                                {previewMetrics.lastClose < 1000
                                                    ? Math.round(
                                                          previewMetrics.lastClose *
                                                              1000,
                                                      ).toLocaleString("vi-VN")
                                                    : Math.round(
                                                          previewMetrics.lastClose,
                                                      ).toLocaleString("vi-VN")}
                                            </span>
                                            <span className="text-xs font-semibold text-slate-400 shrink-0">
                                                VNĐ
                                            </span>
                                        </div>
                                        <div className="mt-1 text-[11px] text-slate-500">
                                            Mốc quan sát gần nhất
                                        </div>
                                    </div>

                                    {/* Card 2: Giá dự báo mục tiêu */}
                                    <div className="rounded-2xl border border-blue-200/80 bg-blue-50/50 dark:border-blue-900/50 dark:bg-blue-950/30 p-3.5 sm:p-4 min-w-0 flex flex-col justify-between overflow-hidden shadow-xs">
                                        <div className="flex items-center justify-between text-xs font-semibold text-blue-700 dark:text-blue-300">
                                            <span>Dự báo mục tiêu</span>
                                            <Target
                                                size={14}
                                                className="text-blue-500 shrink-0"
                                            />
                                        </div>
                                        <div className="mt-2 flex flex-wrap items-baseline gap-1.5 font-mono">
                                            <span className="text-xl sm:text-2xl font-black text-slate-900 dark:text-white truncate">
                                                {previewMetrics.targetPrice <
                                                1000
                                                    ? Math.round(
                                                          previewMetrics.targetPrice *
                                                              1000,
                                                      ).toLocaleString("vi-VN")
                                                    : Math.round(
                                                          previewMetrics.targetPrice,
                                                      ).toLocaleString("vi-VN")}
                                            </span>
                                            <span
                                                className={`inline-flex items-center gap-0.5 text-[11px] font-bold px-1.5 py-0.5 rounded-md shrink-0 ${
                                                    previewMetrics.isUp
                                                        ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30"
                                                        : "bg-rose-500/15 text-rose-600 dark:text-rose-400 border border-rose-500/30"
                                                }`}
                                            >
                                                {previewMetrics.isUp ? (
                                                    <ArrowUpRight size={11} />
                                                ) : (
                                                    <ArrowDownRight size={11} />
                                                )}
                                                {previewMetrics.isUp ? "+" : ""}
                                                {previewMetrics.diffPercent.toFixed(
                                                    2,
                                                )}
                                                %
                                            </span>
                                        </div>
                                        <div className="mt-1 text-[11px] text-slate-500">
                                            Sau {previewMetrics.sessions} phiên
                                            giao dịch
                                        </div>
                                    </div>

                                    {/* Card 3: Xác suất tăng */}
                                    <div className="rounded-2xl border border-indigo-200/80 bg-indigo-50/50 dark:border-indigo-900/50 dark:bg-indigo-950/30 p-3.5 sm:p-4 min-w-0 flex flex-col justify-between overflow-hidden shadow-xs">
                                        <div className="flex items-center justify-between text-xs font-semibold text-indigo-700 dark:text-indigo-300">
                                            <span>Xác suất tăng</span>
                                            <TrendingUp
                                                size={14}
                                                className="text-indigo-500 shrink-0"
                                            />
                                        </div>
                                        <div className="mt-2 font-mono text-xl sm:text-2xl font-black text-indigo-600 dark:text-indigo-400 truncate">
                                            {typeof preview.long_term_trend_probability ===
                                            "number"
                                                ? percentage.format(
                                                      preview.long_term_trend_probability,
                                                  )
                                                : "--"}
                                        </div>
                                        <div className="mt-1 text-[11px] text-slate-500">
                                            Xác suất p_ensemble từ backend
                                        </div>
                                    </div>
                                </div>

                                {/* 3. VIEW MODE TOGGLE & CHART CONTAINER */}
                                <div className="rounded-2xl border border-slate-200/80 bg-slate-900 p-4 sm:p-5 shadow-lg dark:border-slate-800">
                                    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3 mb-4">
                                        <div className="flex items-center gap-2 flex-wrap">
                                            <BarChart3 className="h-4 w-4 text-blue-400 shrink-0" />
                                            <span className="text-sm font-bold text-white whitespace-nowrap">
                                                Quỹ đạo biến động giá dự kiến
                                            </span>
                                            <span className="text-xs text-slate-400 hidden sm:inline">
                                                (Di chuột qua từng điểm để xem
                                                chi tiết)
                                            </span>
                                        </div>

                                        {/* Toggle Tabs */}
                                        <div className="flex items-center gap-1 rounded-xl bg-slate-800/90 p-1 text-xs">
                                            <button
                                                type="button"
                                                onClick={() =>
                                                    setViewMode("interactive")
                                                }
                                                className={`px-3 py-1.5 rounded-lg font-semibold transition-all cursor-pointer ${
                                                    viewMode === "interactive"
                                                        ? "bg-blue-600 text-white shadow-xs"
                                                        : "text-slate-400 hover:text-white"
                                                }`}
                                            >
                                                Biểu đồ Tương tác AI
                                            </button>
                                            {preview.price_forecast
                                                ?.chart_path && (
                                                <button
                                                    type="button"
                                                    onClick={() =>
                                                        setViewMode("technical")
                                                    }
                                                    className={`px-3 py-1.5 rounded-lg font-semibold transition-all cursor-pointer ${
                                                        viewMode === "technical"
                                                            ? "bg-blue-600 text-white shadow-xs"
                                                            : "text-slate-400 hover:text-white"
                                                    }`}
                                                >
                                                    Đồ thị Kỹ thuật Full-HD
                                                </button>
                                            )}
                                        </div>
                                    </div>

                                    {/* Chart Display Area */}
                                    {viewMode === "interactive" ? (
                                        <div className="w-full">
                                            <InteractiveForecastVisual
                                                prediction={preview}
                                            />
                                        </div>
                                    ) : (
                                        preview.price_forecast?.chart_path && (
                                            <div className="relative aspect-[21/9] min-h-[360px] w-full overflow-hidden rounded-xl bg-slate-950 border border-slate-800">
                                                <Image
                                                    src={`/${preview.price_forecast.chart_path.replace(/^\/+/, "")}`}
                                                    alt={`Biểu đồ dự báo ${preview.symbol}`}
                                                    fill
                                                    sizes="96vw"
                                                    unoptimized
                                                    className="object-contain"
                                                />
                                            </div>
                                        )
                                    )}
                                </div>

                                {/* 4. SESSION-BY-SESSION PREDICTION BREAKDOWN TABLE */}
                                {previewMetrics.forecast.length > 0 && (
                                    <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800 overflow-hidden">
                                        <div className="bg-slate-50/90 dark:bg-slate-900/80 px-4 py-3 border-b border-slate-200/80 dark:border-slate-800 flex items-center justify-between">
                                            <span className="text-xs font-bold text-slate-800 dark:text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
                                                <Calendar
                                                    size={13}
                                                    className="text-blue-500"
                                                />{" "}
                                                Chi tiết dự báo từng phiên tiếp
                                                theo
                                            </span>
                                            <span className="text-[11px] text-slate-500">
                                                Tổng cộng{" "}
                                                {previewMetrics.forecast.length}{" "}
                                                phiên dự báo
                                            </span>
                                        </div>
                                        <div className="overflow-x-auto max-h-56">
                                            <table className="w-full text-xs text-left">
                                                <thead className="bg-slate-100/60 dark:bg-slate-800/40 text-[11px] text-slate-500 sticky top-0 backdrop-blur-xs">
                                                    <tr>
                                                        <th className="px-4 py-2">
                                                            Phiên
                                                        </th>
                                                        <th className="px-4 py-2">
                                                            Ngày dự kiến
                                                        </th>
                                                        <th className="px-4 py-2 text-right">
                                                            Giá dự báo (VNĐ)
                                                        </th>
                                                        <th className="px-4 py-2 text-right">
                                                            So với giá hiện tại
                                                        </th>
                                                    </tr>
                                                </thead>
                                                <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
                                                    {previewMetrics.forecast.map(
                                                        (f, idx) => {
                                                            const pClose =
                                                                Number(
                                                                    f.predicted_close,
                                                                ) || 0;
                                                            const pDiff =
                                                                previewMetrics.lastClose >
                                                                0
                                                                    ? ((pClose -
                                                                          previewMetrics.lastClose) /
                                                                          previewMetrics.lastClose) *
                                                                      100
                                                                    : 0;
                                                            const isPtUp =
                                                                pDiff >= 0;
                                                            return (
                                                                <tr
                                                                    key={idx}
                                                                    className="hover:bg-slate-50/50 dark:hover:bg-slate-900/40"
                                                                >
                                                                    <td className="px-4 py-2 font-mono font-bold text-slate-700 dark:text-slate-300">
                                                                        T+
                                                                        {idx +
                                                                            1}
                                                                    </td>
                                                                    <td className="px-4 py-2 text-slate-500">
                                                                        {f.date
                                                                            ? f.date.slice(
                                                                                  0,
                                                                                  10,
                                                                              )
                                                                            : `Phiên ${idx + 1}`}
                                                                    </td>
                                                                    <td className="px-4 py-2 text-right font-mono font-bold text-slate-900 dark:text-white">
                                                                        {formatPrice(
                                                                            pClose,
                                                                        )}
                                                                    </td>
                                                                    <td className="px-4 py-2 text-right">
                                                                        <span
                                                                            className={`font-mono font-bold ${isPtUp ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}`}
                                                                        >
                                                                            {isPtUp
                                                                                ? "+"
                                                                                : ""}
                                                                            {pDiff.toFixed(
                                                                                2,
                                                                            )}
                                                                            %
                                                                        </span>
                                                                    </td>
                                                                </tr>
                                                            );
                                                        },
                                                    )}
                                                </tbody>
                                            </table>
                                        </div>
                                    </div>
                                )}
                            </div>
                        </>
                    )}
                </DialogContent>
            </Dialog>
        </div>
    );
}
