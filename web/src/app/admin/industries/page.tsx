"use client";

import { useEffect, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { AppDispatch, RootState } from "@/redux/store";
import { TableCustom } from "@/share/components/admin/TableCustom";
import { industryColumns } from "./const";
import { fetchIndustriesQuery } from "@/store/industries/industries.api";

export default function AdminIndustriesPage() {
    const dispatch = useDispatch<AppDispatch>();
    const { list, meta, loading } = useSelector(
        (state: RootState) => state.industries
    );

    const [page, setPage] = useState(1);
    const [limit, setLimit] = useState(10);
    const [filters, setFilters] = useState<Record<string, string>>({});

    useEffect(() => {
        dispatch(fetchIndustriesQuery({ page, limit, filters }));
    }, [dispatch, page, limit, filters]);

    return (
        <div className="p-6 w-full shadow-lg shadow-purple-900/30 h-full">
            <h2
                className="text-[1.5rem] md:text-3xl font-semibold 
  bg-gradient-to-r from-[#6A5AF9] to-[#FF5EDF] 
  bg-clip-text text-transparent tracking-tight mb-8"
            >
                Quản lý nhóm ngành
            </h2>

            <TableCustom
                columns={industryColumns}
                data={list}
                meta={meta}
                loading={loading}
                searchConfig={[{ key: "search", label: "Tìm kiếm ngành" }]}
                onPageChange={setPage}
                onLimitChange={setLimit}
                onFilterChange={setFilters}
            />
        </div>
    );
}
