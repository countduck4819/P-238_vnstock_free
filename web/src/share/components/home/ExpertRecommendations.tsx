"use client";

import { useEffect, useState, useMemo } from "react";
import { useAppDispatch, useAppSelector } from "@/redux/hooks";
import { fetchStockRecsQuery } from "@/store/stock-recommendations/stock-recommendations.api";
import { fetchStockCandleData } from "@/store/stock-symbols/stock-symbols.api";
import RecommendationDetailDialog from "./RecommendationDetailDialog";
import { BadgeStatus } from "./BadgeStatus";
import { StockRecommendationStatus } from "@/share/enum";
import { Loader2, ArrowUpRight, Sparkles, TrendingUp, ShieldAlert, Target } from "lucide-react";

// Dữ liệu khuyến nghị mẫu chất lượng cao khi chạy local hoặc database chưa có seed
const DEFAULT_EXPERT_RECOMMENDATIONS = [
    {
        id: 1,
        stock: {
            code: "VND",
            name: "Công ty Cổ phần Chứng khoán VNDIRECT",
            exchange: "HOSE",
        },
        buyPrice: 15.80,
        targetPrice: 20.00,
        stopLossPrice: 14.00,
        status: StockRecommendationStatus.ACTIVE,
        note: "Cổ phiếu tích nền 5 tháng, lực cầu gia tăng mạnh tại vùng hỗ trợ MA50. Dòng tiền nhóm chứng khoán đang dẫn dắt thị trường bứt phá đỉnh ngắn hạn.",
    },
    {
        id: 2,
        stock: {
            code: "SSI",
            name: "Công ty Cổ phần Chứng khoán SSI",
            exchange: "HOSE",
        },
        buyPrice: 28.50,
        targetPrice: 34.00,
        stopLossPrice: 26.50,
        status: StockRecommendationStatus.ACTIVE,
        note: "Thị phần môi giới tiếp tục dẫn đầu, thanh khoản thị trường cải thiện tạo đà tăng trưởng lợi nhuận cốt lõi trong quý tới.",
    },
    {
        id: 3,
        stock: {
            code: "FPT",
            name: "Công ty Cổ phần FPT",
            exchange: "HOSE",
        },
        buyPrice: 132.00,
        targetPrice: 155.00,
        stopLossPrice: 124.00,
        status: StockRecommendationStatus.ACTIVE,
        note: "Mảng xuất khẩu phần mềm và chuyển đổi số AI duy trì tăng trưởng trên 25%/năm. Cổ phiếu phòng thủ cơ bản vững chắc nhất thị trường.",
    },
    {
        id: 4,
        stock: {
            code: "HPG",
            name: "Công ty Cổ phần Tập đoàn Hòa Phát",
            exchange: "HOSE",
        },
        buyPrice: 27.20,
        targetPrice: 32.50,
        stopLossPrice: 25.50,
        status: StockRecommendationStatus.ACTIVE,
        note: "Kỳ vọng sản lượng từ đại dự án Dung Quất 2 thúc đẩy doanh thu, biên lợi nhuận thép xây dựng phục hồi mạnh.",
    },
    {
        id: 5,
        stock: {
            code: "MWG",
            name: "Công ty Cổ phần Đầu tư Thế Giới Di Động",
            exchange: "HOSE",
        },
        buyPrice: 62.00,
        targetPrice: 75.00,
        stopLossPrice: 58.00,
        status: StockRecommendationStatus.ACTIVE,
        note: "Bách Hóa Xanh bắt đầu đóng góp lợi nhuận ròng, chuỗi Thegioididong và Dienmayxanh tối ưu chi phí thành công.",
    },
];

export default function ExpertRecommendations() {
    const dispatch = useAppDispatch();

    // 🔥 Lấy dữ liệu expert từ redux
    const { list: data, loading }: { list: any; loading: any } = useAppSelector(
        (state) => state.stockRecommendations
    );

    const [prices, setPrices] = useState<Record<string, number>>({});
    const [open, setOpen] = useState(false);
    const [detailItem, setDetailItem] = useState<any>(null);

    // 🔥 Fetch EXPERT data khi component mount
    useEffect(() => {
        dispatch(fetchStockRecsQuery({ page: 1, limit: 10 }));
    }, [dispatch]);

    // Lựa chọn dữ liệu hiển thị (ưu tiên dữ liệu Redux/DB, fallback sang mock mẫu)
    const displayList = useMemo(() => {
        if (Array.isArray(data) && data.length > 0) {
            return data;
        }
        return DEFAULT_EXPERT_RECOMMENDATIONS;
    }, [data]);

    // 🔥 Lấy giá nến realtime từng mã
    useEffect(() => {
        if (!Array.isArray(displayList) || displayList.length === 0) return;

        displayList.forEach((item) => {
            const symbol = item?.stock?.code;
            if (!symbol) return;

            dispatch(fetchStockCandleData(symbol)).then((res: any) => {
                if (res?.payload?.length > 0) {
                    const last = res.payload[res.payload.length - 1].close;
                    setPrices((prev) => ({
                        ...prev,
                        [symbol]: last,
                    }));
                }
            });
        });
    }, [displayList, dispatch]);

    if (loading && (!data || data.length === 0)) {
        return (
            <div className="flex flex-col items-center justify-center py-12 text-slate-500 dark:text-slate-400 gap-3">
                <Loader2 className="w-6 h-6 animate-spin text-indigo-600 dark:text-indigo-400" />
                <p className="text-xs font-medium">Đang tải dữ liệu khuyến nghị chuyên gia...</p>
            </div>
        );
    }

    return (
        <>
            <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800 overflow-hidden bg-white dark:bg-slate-900 shadow-sm">
                <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse min-w-[760px]">
                        <thead>
                            <tr className="border-b border-slate-200/80 dark:border-slate-800 bg-slate-50/90 dark:bg-slate-800/70 text-[11px] font-bold text-slate-600 dark:text-slate-300 uppercase tracking-wider">
                                <th className="py-3.5 px-4 text-center">Mã CP</th>
                                <th className="py-3.5 px-4 text-center">Giá mua (Entry)</th>
                                <th className="py-3.5 px-4 text-center">Mục tiêu (Target)</th>
                                <th className="py-3.5 px-4 text-center">Cắt lỗ (Stop)</th>
                                <th className="py-3.5 px-4">Nhận định chuyên gia</th>
                                <th className="py-3.5 px-4 text-center">Giá hiện tại</th>
                                <th className="py-3.5 px-4 text-center">Thao tác</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80 text-xs">
                            {displayList.map((i: any, index: number) => {
                                const currentPrice = prices?.[i.stock?.code];
                                const buyPrice = Number(i.buyPrice) || 0;
                                const targetPrice = Number(i.targetPrice) || 0;
                                const stopLossPrice = Number(i.stopLossPrice) || 0;
                                const upside = buyPrice > 0 ? (((targetPrice - buyPrice) / buyPrice) * 100).toFixed(1) : "0";

                                return (
                                    <tr
                                        key={`${i.id}-${index}`}
                                        onClick={() => {
                                            setDetailItem(i);
                                            setOpen(true);
                                        }}
                                        className="hover:bg-slate-50/80 dark:hover:bg-slate-800/50 transition-colors cursor-pointer group"
                                    >
                                        <td className="py-3.5 px-4 text-center">
                                            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-indigo-500/10 dark:bg-indigo-500/20 text-indigo-600 dark:text-indigo-400 font-bold font-mono text-xs border border-indigo-500/20 group-hover:border-indigo-500/40 transition-colors">
                                                <span>{i.stock?.code}</span>
                                            </div>
                                        </td>

                                        <td className="py-3.5 px-4 text-center font-mono font-bold text-amber-600 dark:text-amber-400">
                                            {buyPrice.toFixed(2)}
                                        </td>

                                        <td className="py-3.5 px-4 text-center">
                                            <div className="flex flex-col items-center">
                                                <span className="font-mono font-bold text-emerald-600 dark:text-emerald-400">
                                                    {targetPrice.toFixed(2)}
                                                </span>
                                                <span className="text-[10px] text-emerald-600 dark:text-emerald-400 font-semibold">
                                                    (+{upside}%)
                                                </span>
                                            </div>
                                        </td>

                                        <td className="py-3.5 px-4 text-center font-mono font-bold text-rose-600 dark:text-rose-400">
                                            {stopLossPrice.toFixed(2)}
                                        </td>

                                        <td className="py-3.5 px-4 max-w-[260px]">
                                            <p className="line-clamp-2 text-slate-600 dark:text-slate-300 leading-snug text-xs">
                                                {i.note || "—"}
                                            </p>
                                        </td>

                                        <td className="py-3.5 px-4 text-center">
                                            {i.status === StockRecommendationStatus.STOP_LOSS ||
                                            i.status === StockRecommendationStatus.TARGET_HIT ? (
                                                <BadgeStatus status={i.status as any} />
                                            ) : (
                                                <span className="font-mono font-bold text-indigo-600 dark:text-indigo-400 text-sm">
                                                    {currentPrice !== undefined ? Number(currentPrice).toFixed(2) : "..."}
                                                </span>
                                            )}
                                        </td>

                                        <td className="py-3.5 px-4 text-center">
                                            <button
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    setDetailItem(i);
                                                    setOpen(true);
                                                }}
                                                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl text-xs font-semibold bg-indigo-50 dark:bg-indigo-950/50 text-indigo-600 dark:text-indigo-400 hover:bg-indigo-600 hover:text-white dark:hover:bg-indigo-600 dark:hover:text-white transition-all cursor-pointer shadow-2xs"
                                            >
                                                <span>Xem chi tiết</span>
                                                <ArrowUpRight size={13} />
                                            </button>
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            </div>

            {open && (
                <RecommendationDetailDialog
                    open={open}
                    onOpenChange={setOpen}
                    item={detailItem}
                    price={
                        detailItem ? prices[detailItem.stock?.code] : undefined
                    }
                />
            )}
        </>
    );
}
