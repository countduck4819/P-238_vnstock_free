"use client";

import { useEffect, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { toast } from "react-toastify";

import { AppDispatch, RootState } from "@/redux/store";

import {
    fetchPremiumOrdersQuery,
    updatePremiumOrder,
    deletePremiumOrder,
} from "@/store/premium-orders/premium-orders.api";

import { TableCustom } from "@/share/components/admin/TableCustom";
import { CrudDialog } from "@/share/components/admin/CrudDialog";

import { premiumOrderColumns, usePremiumOrderFields } from "./const";
import { PremiumOrder } from "@/store/premium-orders/premium-orders.reducer";

export default function AdminPremiumOrdersPage() {
    const dispatch = useDispatch<AppDispatch>();

    const { list, meta, loading } = useSelector(
        (state: RootState) => state.premiumOrders
    );

    const [page, setPage] = useState(1);
    const [limit, setLimit] = useState(10);
    const [filters, setFilters] = useState<Record<string, string>>({});

    const [dialog, setDialog] = useState<{
        open: boolean;
        mode: "edit" | "delete" | null;
        item?: PremiumOrder | null;
    }>({ open: false, mode: null, item: null });

    const fields = usePremiumOrderFields();

    useEffect(() => {
        dispatch(fetchPremiumOrdersQuery({ page, limit, filters }));
    }, [page, limit, filters]);

    const handleSubmit = async (data: any, mode: any) => {
        try {
            if (mode === "edit") {
                await dispatch(
                    updatePremiumOrder({
                        id: Number(data.id),
                        data,
                    })
                ).unwrap();
                toast.success("Cập nhật hóa đơn thành công!");
            } else {
                await dispatch(deletePremiumOrder(Number(data.id))).unwrap();
                toast.success("Xóa hóa đơn thành công!");
            }

            setDialog({ open: false, mode: null });
            dispatch(fetchPremiumOrdersQuery({ page, limit, filters }));
        } catch (err: any) {
            toast.error(err || "Thao tác thất bại!");
        }
    };

    return (
        <>
            <div className="p-6 w-full shadow-lg shadow-purple-900/30 h-full">
                <h2 className="text-3xl font-semibold bg-gradient-to-r from-[#6A5AF9] to-[#FF5EDF] bg-clip-text text-transparent mb-8">
                    Quản lý hóa đơn Premium
                </h2>

                <TableCustom
                    columns={premiumOrderColumns}
                    data={list}
                    meta={meta}
                    loading={loading}
                    searchConfig={[
                        { key: "orderCode", label: "Mã đơn" },
                        { key: "fullName", label: "Họ tên" },
                    ]}
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
                entityName="hóa đơn"
                onClose={() => setDialog({ open: false, mode: null })}
                onSubmit={handleSubmit}
                fields={fields}
            />
        </>
    );
}
