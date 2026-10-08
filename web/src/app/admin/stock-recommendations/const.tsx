"use client";

import { useEffect, useMemo, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { Button } from "@/components/ui/button";
import { Edit, Trash2 } from "lucide-react";
import { Column } from "@/share/components/admin/TableCustom";
import { CrudField } from "@/share/components/admin/CrudDialog";
import BadgeTag from "@/share/components/admin/Badge";
import { api } from "@/utils/axiosInstance";
import {
    StockRecStatus,
    StockRecommendation,
} from "@/store/stock-recommendations/stock-recommendations.reducer";
import { AppDispatch, RootState } from "@/redux/store";
import { fetchStockCandleData } from "@/store/stock-symbols/stock-symbols.api";

/* =============================
   📊 CỘT HIỂN THỊ TRONG BẢNG
============================= */
export const stockRecColumns: Column<StockRecommendation>[] = [
    {
        key: "stock",
        header: "Mã cổ phiếu",
        render: (item) => item.stock?.code || "—",
    },
    {
        key: "buyPrice",
        header: "Giá mua",
        render: (item) => (
            <span className="text-yellow-400 font-medium">
                {parseFloat(`${item?.buyPrice}`).toFixed(2)}
            </span>
        ),
    },
    {
        key: "targetPrice",
        header: "Giá chốt lời",
        render: (item) => (
            <span className="text-green-400 font-medium">
                {parseFloat(`${item.targetPrice}`).toFixed(2)}
            </span>
        ),
    },
    {
        key: "stopLossPrice",
        header: "Giá cắt lỗ",
        render: (item) => (
            <span className="text-red-400 font-medium">
                {parseFloat(`${item.stopLossPrice}`).toFixed(2)}
            </span>
        ),
    },
    { key: "note", header: "Mô tả" },
    {
        key: "status",
        header: "Trạng thái",
        render: (item) => {
            const map: Record<
                StockRecStatus,
                { label: string; color: string }
            > = {
                ACTIVE: {
                    label: "Đang mở",
                    color: "bg-blue-500/20 text-blue-400",
                },
                TARGET_HIT: {
                    label: "Chốt lời",
                    color: "bg-green-500/20 text-green-400",
                },
                STOP_LOSS: {
                    label: "Cắt lỗ",
                    color: "bg-red-500/20 text-red-400",
                },
                CLOSED: {
                    label: "Đã đóng",
                    color: "bg-gray-500/20 text-gray-400",
                },
            };

            const status = item.status as StockRecStatus;
            const { label, color } = map[status] || map.CLOSED;
            return <BadgeTag label={label} color={color} />;
        },
    },
    {
        key: "actions",
        header: "Thao tác",
        render: (item, actions) => (
            <div className="flex gap-2">
                <Button
                    size="icon"
                    variant="ghost"
                    className="text-indigo-400 hover:text-indigo-300"
                    onClick={() => actions?.onEditClick?.(item)}
                >
                    <Edit className="h-4 w-4" />
                </Button>
                <Button
                    size="icon"
                    variant="ghost"
                    className="text-red-400 hover:text-red-300"
                    onClick={() => actions?.onDeleteClick?.(item)}
                >
                    <Trash2 className="h-4 w-4" />
                </Button>
            </div>
        ),
    },
];

/* =============================
   🧩 FIELD FORM CRUD
============================= */
export function useStockRecFields(): CrudField[] {
    const dispatch = useDispatch<AppDispatch>();
    const { candleData } = useSelector(
        (state: RootState) => state.stockSymbols
    );
    const [stockOptions, setStockOptions] = useState<
        { label: string; value: string; code: string }[]
    >([]);

    useEffect(() => {
        let mounted = true;
        api.get("/stock-recommendations/available/stocks")
            .then((res) => {
                if (!mounted) return;
                const data = res.data?.data || [];
                setStockOptions(
                    data.map((s: any) => ({
                        label: `${s.code} - ${s.name}`,
                        value: String(s.id),
                        code: s.code,
                    }))
                );
            })
            .catch(() => mounted && setStockOptions([]));
        return () => {
            mounted = false;
        };
    }, []);

    return useMemo(
        () => [
            {
                name: "stockId",
                label: "Mã cổ phiếu",
                type: "select-search",
                required: true,
                options: stockOptions,
                placeholder: "Tìm hoặc chọn mã cổ phiếu",
                isEditMode: true,
                onSelect: async (stockId, updateForm) => {
                    try {
                        const selected = stockOptions.find(
                            (s) => s.value === stockId
                        );
                        if (!selected?.code) return;

                        const res = await dispatch(
                            fetchStockCandleData(selected.code)
                        ).unwrap();

                        const last = res?.[res.length - 1];
                        if (!last) return;

                        const close = +last.close || 0;
                        const target = +(close * 1.1).toFixed(2);
                        const stopLoss = +(close * 0.9).toFixed(2);

                        updateForm({
                            buyPrice: close,
                            targetPrice: target,
                            stopLossPrice: stopLoss,
                        });
                    } catch (err) {
                        console.error("Lỗi lấy dữ liệu giá:", err);
                    }
                },
            },
            {
                name: "buyPrice",
                label: "Giá mua",
                type: "number",
                required: true,
                placeholder: "Nhập giá mua",
            },
            {
                name: "targetPrice",
                label: "Giá chốt lời",
                type: "number",
                required: true,
                placeholder: "Nhập giá chốt lời",
                validate: (v, all) => {
                    const buy = parseFloat(all?.buyPrice ?? 0);
                    const tar = parseFloat(v ?? 0);
                    if (buy && tar < buy) return "Giá chốt lời phải ≥ giá mua";
                    return null;
                },
            },
            {
                name: "stopLossPrice",
                label: "Giá cắt lỗ",
                type: "number",
                required: true,
                placeholder: "Nhập giá cắt lỗ",
                validate: (v, all) => {
                    const buy = parseFloat(all?.buyPrice ?? 0);
                    const sl = parseFloat(v ?? 0);
                    if (buy && sl > buy) return "Giá cắt lỗ phải ≤ giá mua";
                    return null;
                },
            },

            {
                name: "note",
                label: "Ghi chú",
                type: "textarea",
                placeholder: "Nhập ghi chú (nếu có)",
            },
        ],
        [stockOptions, dispatch, candleData]
    );
}
