"use client";

import { Column } from "@/share/components/admin/TableCustom";
import { CrudField } from "@/share/components/admin/CrudDialog";
import { Button } from "@/components/ui/button";
import { Edit, Trash2 } from "lucide-react";
import BadgeTag from "@/share/components/admin/Badge";
import {
    PremiumOrder,
    PremiumOrderStatus,
} from "@/store/premium-orders/premium-orders.reducer";

export const premiumOrderColumns: Column<PremiumOrder>[] = [
    {
        key: "orderCode",
        header: "Mã đơn",
    },
    {
        key: "user",
        header: "User",
        render: (item) =>
            item.user
                ? `${item.user.username} (${item.user.fullName || "No name"})`
                : "—",
    },
    {
        key: "amount",
        header: "Số tiền",
        render: (item) => (
            <span className="text-yellow-400">
                {Number(item.amount).toLocaleString()} đ
            </span>
        ),
    },
    {
        key: "status",
        header: "Trạng thái",
        render: (item) => {
            const map: Record<
                PremiumOrderStatus,
                { label: string; color: string }
            > = {
                PENDING: {
                    label: "Đợi thanh toán",
                    color: "bg-gray-500/20 text-gray-300",
                },
                PAID: {
                    label: "Đã thanh toán",
                    color: "bg-green-500/20 text-green-400",
                },
                CANCEL: {
                    label: "Đã hủy",
                    color: "bg-red-500/20 text-red-400",
                },
            };

            const { label, color } = map[item.status];
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
                    className="text-indigo-400"
                    onClick={() => actions?.onEditClick?.(item)}
                >
                    <Edit className="h-4 w-4" />
                </Button>

                <Button
                    size="icon"
                    variant="ghost"
                    className="text-red-400"
                    onClick={() => actions?.onDeleteClick?.(item)}
                >
                    <Trash2 className="h-4 w-4" />
                </Button>
            </div>
        ),
    },
];

export function usePremiumOrderFields(): CrudField[] {
    return [
        {
            name: "orderCode",
            label: "Mã đơn",
            type: "input",
            disabled: true,
        },
        {
            name: "userId",
            label: "User ID",
            type: "input",
            disabled: true,
        },
        {
            name: "amount",
            label: "Số tiền",
            type: "number",
            disabled: true,
        },
        {
            name: "status",
            label: "Trạng thái",
            type: "select",
            options: [
                { label: "PENDING", value: "PENDING" },
                { label: "PAID", value: "PAID" },
                { label: "CANCEL", value: "CANCEL" },
            ],
            required: true,
        },
        {
            name: "transactionId",
            label: "Mã giao dịch",
            type: "input",
            placeholder: "Nhập mã giao dịch (nếu có)",
        },
        {
            name: "paymentMethod",
            label: "Phương thức thanh toán",
            type: "input",
            placeholder: "VD: momo, banking...",
        },
    ];
}
