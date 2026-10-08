"use client";

import { useEffect, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { toast } from "react-toastify";
import {
    createStockRec,
    deleteStockRec,
    fetchStockRecsQuery,
    updateStockRec,
} from "@/store/stock-recommendations/stock-recommendations.api";
import { AppDispatch, RootState } from "@/redux/store";
import { TableCustom } from "@/share/components/admin/TableCustom";
import { CrudDialog } from "@/share/components/admin/CrudDialog";
import { StockRecommendation } from "@/store/stock-recommendations/stock-recommendations.reducer";
import { stockRecColumns, useStockRecFields } from "./const";

export default function AdminStockRecommendationsPage() {
    const dispatch = useDispatch<AppDispatch>();
    const { list, meta, loading } = useSelector(
        (state: RootState) => state.stockRecommendations
    );

    const [page, setPage] = useState(1);
    const [limit, setLimit] = useState(10);
    const [filters, setFilters] = useState<Record<string, string>>({});
    const [dialog, setDialog] = useState<{
        open: boolean;
        mode: "add" | "edit" | "delete" | null;
        item?: StockRecommendation | null;
    }>({ open: false, mode: null, item: null });

    const fields = useStockRecFields();

    useEffect(() => {
        dispatch(fetchStockRecsQuery({ page, limit, filters }));
    }, [dispatch, page, limit, filters]);

    const handleSubmit = async (
        data: Partial<StockRecommendation>,
        mode: "add" | "edit" | "delete"
    ) => {
        try {
            if (mode === "add") {
                await dispatch(createStockRec(data as any)).unwrap();
                toast.success("Tạo khuyến nghị thành công!");
            } else if (mode === "edit") {
                await dispatch(
                    updateStockRec({ id: data.id as string, data })
                ).unwrap();
                toast.success("Cập nhật khuyến nghị thành công!");
            } else if (mode === "delete") {
                await dispatch(deleteStockRec(data.id as string)).unwrap();
                toast.success("Xoá khuyến nghị thành công!");
            }

            // 🔁 Refresh data sau thao tác
            setDialog({ open: false, mode: null });
            dispatch(fetchStockRecsQuery({ page, limit, filters }));
        } catch (error: any) {
            toast.error(error || "Thao tác thất bại!");
        }
    };

    return (
        <>
            <div className="p-6 w-full shadow-lg shadow-purple-900/30 h-full">
                <h2 className="text-3xl font-semibold bg-gradient-to-r from-[#6A5AF9] to-[#FF5EDF] bg-clip-text text-transparent mb-8">
                    Quản lý khuyến nghị cổ phiếu
                </h2>

                <TableCustom
                    columns={stockRecColumns}
                    data={list}
                    meta={meta}
                    loading={loading}
                    searchConfig={[{ key: "search", label: "Mã cổ phiếu" }]}
                    onAddClick={() =>
                        setDialog({ open: true, mode: "add", item: null })
                    }
                    onEditClick={(item) =>
                        setDialog({ open: true, mode: "edit", item })
                    }
                    onDeleteClick={(item) =>
                        setDialog({ open: true, mode: "delete", item })
                    }
                    onPageChange={setPage}
                    onLimitChange={setLimit}
                    onFilterChange={setFilters}
                />
            </div>

            <CrudDialog
                open={dialog.open}
                mode={dialog.mode}
                item={dialog.item}
                entityName="khuyến nghị"
                onClose={() => setDialog({ open: false, mode: null })}
                onSubmit={handleSubmit}
                fields={fields}
            />
        </>
    );
}
