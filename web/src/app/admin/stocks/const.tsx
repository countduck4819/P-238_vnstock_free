import { Column } from "@/share/components/admin/TableCustom";

export interface Stock {
    id: number;
    code: string;
    name: string;
    industryId: number;
    industry?: { id: number; name: string };
}

export const stockColumns: Column<Stock>[] = [
    { key: "id", header: "ID" },
    { key: "code", header: "Mã cổ phiếu" },
    { key: "name", header: "Tên cổ phiếu" },
    {
        key: "industry",
        header: "Ngành",
        render: (item) => item.industry?.name || "—",
    },
];
