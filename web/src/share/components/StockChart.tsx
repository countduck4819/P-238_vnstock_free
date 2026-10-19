"use client";

import {
    CandlestickSeries,
    ColorType,
    CrosshairMode,
    HistogramSeries,
    LineSeries,
    createChart,
    type Time,
} from "lightweight-charts";
import { useEffect, useRef } from "react";
import { pythonApiUrl } from "@/utils/pythonApi";

interface Candle {
    time: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume?: number;
}

const HISTORY_START = "2015-01-01";

export default function StockChart({ symbol = "VCB" }: { symbol?: string }) {
    const containerRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (!containerRef.current) return;

        const container = containerRef.current;
        const chart = createChart(container, {
            width: container.clientWidth,
            height: 600,
            layout: {
                background: { type: ColorType.Solid, color: "#ffffff" },
                textColor: "#1e293b",
            },
            grid: {
                vertLines: { color: "#e5e7eb" },
                horzLines: { color: "#e5e7eb" },
            },
            crosshair: { mode: CrosshairMode.Normal },
            timeScale: {
                borderColor: "#cbd5e1",
                timeVisible: false,
            },
            rightPriceScale: { borderColor: "#cbd5e1" },
        });

        const candleSeries = chart.addSeries(CandlestickSeries, {
            upColor: "#00a884",
            borderUpColor: "#00a884",
            wickUpColor: "#00a884",
            downColor: "#ef4444",
            borderDownColor: "#ef4444",
            wickDownColor: "#ef4444",
        });

        const volumeSeries = chart.addSeries(HistogramSeries, {
            priceFormat: { type: "volume" },
            priceScaleId: "",
        });
        volumeSeries.priceScale().applyOptions({
            scaleMargins: { top: 0.8, bottom: 0 },
        });

        const ma10Series = chart.addSeries(LineSeries, {
            color: "#4338ca",
            lineWidth: 2,
        });

        const ma50Series = chart.addSeries(LineSeries, {
            color: "#38bdf8",
            lineWidth: 2,
        });

        const calcMA = (data: Candle[], len: number) =>
            data
                .map((item, index) => {
                    if (index + 1 < len) return null;

                    const slice = data.slice(index + 1 - len, index + 1);
                    const avg =
                        slice.reduce((sum, candle) => sum + candle.close, 0) /
                        len;

                    return {
                        time: item.time as Time,
                        value: avg,
                    };
                })
                .filter(Boolean) as { time: Time; value: number }[];

        const abortController = new AbortController();

        async function fetchData() {
            const params = new URLSearchParams({
                start: HISTORY_START,
                end: new Date().toISOString().slice(0, 10),
            });

            const res = await fetch(
                pythonApiUrl(`/stock/${symbol.toUpperCase()}?${params}`),
                { signal: abortController.signal },
            );

            if (!res.ok) {
                throw new Error(`Khong the tai du lieu ${symbol}`);
            }

            const data = (await res.json()) as Candle[];
            const candles = data
                .filter((item) => item?.time && Number.isFinite(item.close))
                .sort((a, b) => a.time.localeCompare(b.time));

            candleSeries.setData(
                candles.map((item) => ({
                    time: item.time as Time,
                    open: item.open,
                    high: item.high,
                    low: item.low,
                    close: item.close,
                })),
            );

            volumeSeries.setData(
                candles.map((item) => ({
                    time: item.time as Time,
                    value: item.volume || 0,
                    color: item.close >= item.open ? "#00a884" : "#ef4444",
                })),
            );

            ma10Series.setData(calcMA(candles, 10));
            ma50Series.setData(calcMA(candles, 50));
            chart.timeScale().fitContent();
        }

        fetchData().catch((error) => {
            if (error.name !== "AbortError") {
                console.error("Loi tai du lieu chart:", error);
            }
        });

        const resize = () => {
            chart.applyOptions({ width: container.clientWidth });
        };

        window.addEventListener("resize", resize);

        return () => {
            abortController.abort();
            window.removeEventListener("resize", resize);
            chart.remove();
        };
    }, [symbol]);

    return (
        <div
            ref={containerRef}
            className="h-[600px] w-full rounded-md border shadow"
        />
    );
}
