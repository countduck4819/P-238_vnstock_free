"use client";

import { Column } from "@/share/components/admin/TableCustom";

export interface Industry {
    id: number;
    name: string;
    modifiedAt: string | null;
}

export const industryColumns: Column<Industry>[] = [
    {
        key: "id",
        header: "ID",
    },
    {
        key: "name",
        header: "Tên ngành",
    },
    {
        key: "modifiedAt",
        header: "Ngày cập nhật",
        render: (item) => {
            if (!item.modifiedAt) return "—";
            const date = new Date(item.modifiedAt);
            return isNaN(date.getTime())
                ? "—"
                : date.toLocaleDateString("vi-VN", {
                      day: "2-digit",
                      month: "2-digit",
                      year: "numeric",
                  });
        },
    },
];
