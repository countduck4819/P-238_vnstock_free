import Image from "next/image";
import { Column } from "@/share/components/admin/TableCustom";

export interface StockPrediction {
    id: number;
    ticker: string;
    lastClosePrice: number;
    predictedPrice: number;
    pEnsemble?: number | null;
    chartPath?: string | null;
    predictedOn: string;
}

// Giá lưu dạng float (vd 2.0999999046325684): hiển thị tối đa 3 chữ số thập phân.
const formatPrice = (value: number | string | null | undefined) => {
    const price = Number(value);
    if (value == null || !Number.isFinite(price)) return "—";
    return price.toLocaleString("en-US", { maximumFractionDigits: 3 });
};

export const stockPredictionColumns: Column<StockPrediction>[] = [
    { key: "id", header: "ID" },
    { key: "ticker", header: "Mã" },
    {
        key: "lastClosePrice",
        header: "Giá đóng gần nhất",
        className: "w-32 whitespace-normal",
        render: (item) => formatPrice(item.lastClosePrice),
    },
    {
        key: "predictedPrice",
        header: "Giá dự đoán",
        className: "w-32 whitespace-normal",
        render: (item) => formatPrice(item.predictedPrice),
    },
    {
        key: "pEnsemble",
        header: "Xác suất tăng",
        render: (item) => {
            if (item.pEnsemble == null) return "—";

            const probability = Number(item.pEnsemble);

            if (!Number.isFinite(probability)) return "—";

            return (
                <span className="font-semibold text-emerald-600 dark:text-emerald-400">
                    {(probability * 100).toFixed(2)}%
                </span>
            );
        },
    },
    {
        key: "chartPath",
        header: "Biểu đồ",
        render: (item, actions) =>
            item.chartPath ? (
                <div
                    className="w-16 h-12 relative border rounded overflow-hidden bg-white cursor-pointer"
                    onClick={() => actions?.onPreview?.(`/${item.chartPath}`!)}
                >
                    <Image
                        src={`/${item.chartPath}`}
                        alt={`/charts/${item.ticker}`}
                        fill
                        unoptimized
                        className="object-cover w-full h-auto"
                    />
                </div>
            ) : (
                "—"
            ),
    },
    {
        key: "predictedOn",
        header: "Ngày dự đoán",
        render: (item) => new Date(item.predictedOn).toLocaleString("vi-VN"),
    },
];
