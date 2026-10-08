"use client";

import { useEffect, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { AppDispatch, RootState } from "@/redux/store";
import { TableCustom } from "@/share/components/admin/TableCustom";
import { newsColumns } from "./const";
import { fetchNewsQuery, fetchNewsSearchQuery } from "@/store/news/news.api";

export default function AdminNewsPage() {
    const dispatch = useDispatch<AppDispatch>();
    const {
        list: news,
        meta,
        loading,
        searchList,
        searchMeta,
    } = useSelector((state: RootState) => state.news);

    const [page, setPage] = useState(1);
    const [limit, setLimit] = useState(10);
    const [filters, setFilters] = useState<Record<string, string>>({});

    // 🔍 Nếu có keyword → dùng API search, ngược lại → fetch bình thường
    useEffect(() => {
        const keyword = filters?.news_title?.trim();

        if (keyword) {
            dispatch(fetchNewsSearchQuery({ page, limit, keyword }));
        } else {
            dispatch(fetchNewsQuery({ page, limit }));
        }
    }, [dispatch, page, limit, filters]);

    // 🔁 Quyết định nguồn data hiển thị
    const dataToShow =
        filters?.news_title?.trim() && searchList.length > 0
            ? searchList
            : news;

    const metaToShow =
        filters?.news_title?.trim() && searchMeta?.total ? searchMeta : meta;

    return (
        <div className="p-6 w-full shadow-lg shadow-purple-900/30 h-full">
            <h2
                className="text-[1.5rem] md:text-3xl font-semibold 
        bg-gradient-to-r from-[#6A5AF9] to-[#FF5EDF] 
        bg-clip-text text-transparent tracking-tight mb-8"
            >
                Tin tức thị trường
            </h2>

            <TableCustom
                columns={newsColumns}
                data={dataToShow}
                meta={metaToShow}
                loading={loading}
                searchConfig={[
                    { key: "news_title", label: "Tìm theo tiêu đề" },
                ]}
                onPageChange={setPage}
                onLimitChange={setLimit}
                onFilterChange={setFilters}
            />
        </div>
    );
}
