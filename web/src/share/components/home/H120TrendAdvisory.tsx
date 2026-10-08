"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertCircle, Loader2, RefreshCw, TrendingUp } from "lucide-react";
import { api } from "@/utils/axiosInstance";

type H120Prediction = {
    symbol: string;
    date: string;
    rank: number;
    selected_top_k: boolean;
    continuation_probability_h120: number | null;
};

type H120Payload = {
    trend_type: "short_term";
    as_of_date: string;
    snapshot_date: string;
    deployment_status: string;
    trade_authorized: false;
    advisory: {
        horizon_sessions: number;
        advisory_only: true;
        not_a_trade_instruction: true;
    };
    summary: {
        eligible_rows?: number;
        shortlist_rows?: number;
    };
    predictions: H120Prediction[];
};

const percentage = new Intl.NumberFormat("vi-VN", {
    style: "percent",
    maximumFractionDigits: 1,
});

const dateFormatter = new Intl.DateTimeFormat("vi-VN", {
    dateStyle: "medium",
});

function displayDate(value?: string) {
    if (!value) return "--";
    const date = new Date(`${value.slice(0, 10)}T00:00:00`);
    return Number.isNaN(date.getTime()) ? value : dateFormatter.format(date);
}

export default function H120TrendAdvisory() {
    const [payload, setPayload] = useState<H120Payload | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [showMore, setShowMore] = useState(false);

    const load = async () => {
        setLoading(true);
        setError(null);
        try {
            const response = await api.get("/wave-h120/latest", {
                params: { limit: 50 },
            });
            const data = response.data?.data as H120Payload | undefined;
            // Older vnstock-data deployments do not include trend_type yet;
            // the advisory contract is still valid when the response carries
            // the required safety flag and prediction rows.
            if ((data?.trend_type && data.trend_type !== "short_term") || data?.trade_authorized !== false || !Array.isArray(data?.predictions)) {
                throw new Error("Dữ liệu tư vấn xu hướng không hợp lệ.");
            }
            setPayload(data);
        } catch {
            setPayload(null);
            setError("Chưa thể tải xác suất xu hướng. Vui lòng thử lại sau.");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        void load();
    }, []);

    const visiblePredictions = useMemo(() => {
        if (!payload) return [];
        return payload.predictions.slice(0, showMore ? 50 : 20);
    }, [payload, showMore]);

    return (
        <div className="space-y-4">
            <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs leading-5 text-amber-900 dark:border-amber-900/70 dark:bg-amber-950/30 dark:text-amber-200">
                <div className="flex items-start gap-2">
                    <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                    <p>
                        Xác suất tiếp diễn xu hướng trong 120 phiên, chỉ dùng để tham khảo.
                        Đây không phải khuyến nghị mua/bán và không tự động thực hiện giao dịch.
                    </p>
                </div>
            </div>

            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                    <h3 className="flex items-center gap-2 text-sm font-bold text-slate-900 dark:text-white">
                        <TrendingUp className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
                        Xu hướng ngắn hạn
                    </h3>
                    {payload && (
                        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                            Dữ liệu đến phiên {displayDate(payload.as_of_date)} · snapshot {displayDate(payload.snapshot_date)}
                        </p>
                    )}
                </div>
                <button
                    type="button"
                    onClick={() => void load()}
                    disabled={loading}
                    className="inline-flex h-9 items-center justify-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
                >
                    <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
                    Làm mới
                </button>
            </div>

            {loading && (
                <div className="flex min-h-48 items-center justify-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                    <Loader2 className="h-5 w-5 animate-spin text-emerald-600" />
                    Đang tải dữ liệu xu hướng…
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
                        <div className="rounded-xl bg-slate-50 px-3 py-2 dark:bg-slate-800/70">
                            <p className="text-[11px] text-slate-500 dark:text-slate-400">Mã đủ điều kiện</p>
                            <p className="mt-0.5 text-sm font-bold text-slate-900 dark:text-white">
                                {payload.summary?.eligible_rows ?? "--"}
                            </p>
                        </div>
                        <div className="rounded-xl bg-slate-50 px-3 py-2 dark:bg-slate-800/70">
                            <p className="text-[11px] text-slate-500 dark:text-slate-400">Danh sách hiển thị</p>
                            <p className="mt-0.5 text-sm font-bold text-slate-900 dark:text-white">
                                 {visiblePredictions.length} / {payload.predictions.length}
                            </p>
                        </div>
                    </div>

                    <div className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
                        <div className="overflow-x-auto">
                            <table className="w-full min-w-[500px] border-collapse text-left text-xs">
                                <thead>
                                    <tr className="border-b border-slate-200/80 bg-slate-50/80 text-[11px] font-bold uppercase tracking-wider text-slate-600 dark:border-slate-800 dark:bg-slate-800/60 dark:text-slate-300">
                                        <th className="px-4 py-3.5 text-center">Hạng</th>
                                        <th className="px-4 py-3.5">Mã CP</th>
                                        <th className="px-4 py-3.5 text-center">Xác suất tiếp diễn</th>
                                        <th className="px-4 py-3.5 text-center">Phiên dữ liệu</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                                     {visiblePredictions.map((prediction) => (
                                        <tr key={prediction.symbol} className="transition-colors hover:bg-slate-50/70 dark:hover:bg-slate-800/50">
                                             <td className="px-4 py-3.5 text-center font-mono font-semibold text-slate-600 dark:text-slate-300">
                                                 <div>#{prediction.rank}</div>
                                                 {prediction.selected_top_k && (
                                                     <span className="mt-1 inline-flex rounded-full bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700 dark:text-amber-300">
                                                         Top 10
                                                     </span>
                                                 )}
                                            </td>
                                            <td className="px-4 py-3.5">
                                                <span className="inline-flex rounded-lg bg-emerald-500/10 px-2.5 py-1 text-xs font-bold text-emerald-700 dark:text-emerald-300">
                                                    {prediction.symbol}
                                                </span>
                                            </td>
                                            <td className="px-4 py-3.5 text-center">
                                                <span className="inline-flex rounded-full bg-indigo-500/10 px-2.5 py-1 font-mono font-bold text-indigo-700 dark:text-indigo-300">
                                                    {typeof prediction.continuation_probability_h120 === "number"
                                                        ? percentage.format(prediction.continuation_probability_h120)
                                                        : "--"}
                                                </span>
                                            </td>
                                            <td className="px-4 py-3.5 text-center text-slate-500 dark:text-slate-400">
                                                {displayDate(prediction.date)}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                             </table>
                         </div>
                         {payload.predictions.length > 20 && (
                             <div className="flex items-center justify-between border-t border-slate-200/80 px-4 py-3 text-xs dark:border-slate-800">
                                 <span className="text-slate-500 dark:text-slate-400">
                                     Top 10 là shortlist theo contract; các mã còn lại chỉ để tham khảo/xếp hạng.
                                 </span>
                                 <button
                                     type="button"
                                     onClick={() => setShowMore((value) => !value)}
                                     className="shrink-0 rounded-lg border border-slate-200 px-3 py-1.5 font-semibold text-slate-700 transition hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
                                 >
                                     {showMore ? "Thu gọn" : "Xem thêm Top 50"}
                                 </button>
                             </div>
                         )}
                     </div>
                </>
            )}
        </div>
    );
}
