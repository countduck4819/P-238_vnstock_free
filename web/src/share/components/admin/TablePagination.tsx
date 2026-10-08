"use client";

import { Button } from "@/components/ui/button";
import {
    Select,
    SelectTrigger,
    SelectValue,
    SelectContent,
    SelectItem,
} from "@/components/ui/select";
import { ChevronLeft, ChevronRight, Loader2 } from "lucide-react";
import { useMemo } from "react";

interface TablePaginationProps {
    page: number;
    setPage: (page: number) => void;
    totalPages: number;
    loading?: boolean;
    limit: number;
    setLimit: (limit: number) => void;
}

export function TablePagination({
    page,
    setPage,
    totalPages,
    loading = false,
    limit,
    setLimit,
}: TablePaginationProps) {
    const handleChangePage = (newPage: number) => {
        if (newPage >= 1 && newPage <= totalPages && newPage !== page) {
            setPage(newPage);
        }
    };

    const limitOptions = [10, 20, 50, 100];

    const pages = useMemo(
        () => Array.from({ length: totalPages }, (_, i) => i + 1),
        [totalPages]
    );

    const visiblePages = useMemo(() => {
        const range = 2; // 2 trước + 2 sau
        const start = Math.max(1, page - range);
        const end = Math.min(totalPages, page + range);
        return pages.slice(start - 1, end);
    }, [page, pages, totalPages]);

    return (
        <div className="flex items-center justify-between px-4 py-3 rounded-lg border border-purple-500/30 bg-gradient-to-r from-[#1B1234] to-[#241B46] shadow-md shadow-purple-900/30">
            <div className="flex items-center gap-2 text-sm text-gray-200">
                <span>Hiển thị</span>
                <Select
                    value={String(limit)}
                    onValueChange={(v) => {
                        setLimit(Number(v));
                        setPage(1);
                    }}
                >
                    <SelectTrigger className="w-[5rem] bg-[#2A1F4B] border-purple-500/30 text-purple-300">
                        <SelectValue placeholder={limit} />
                    </SelectTrigger>
                    <SelectContent>
                        {limitOptions.map((item) => (
                            <SelectItem key={item} value={String(item)}>
                                {item}
                            </SelectItem>
                        ))}
                    </SelectContent>
                </Select>
                <span>dòng</span>
            </div>

            <div className="flex items-center gap-2">
                <div className="text-sm text-gray-200">
                    Trang{" "}
                    <span className="font-semibold text-purple-300">
                        {page}
                    </span>{" "}
                    / <span className="text-gray-400">{totalPages || 1}</span>
                </div>

                <Button
                    size="icon"
                    variant="ghost"
                    disabled={page <= 1 || loading}
                    onClick={() => handleChangePage(page - 1)}
                    className="hover:bg-purple-700/30 text-gray-200 disabled:opacity-40 rounded-full"
                >
                    <ChevronLeft className="h-4 w-4" />
                </Button>

                {visiblePages.map((p) => (
                    <Button
                        key={p}
                        variant={p === page ? "default" : "ghost"}
                        disabled={loading}
                        onClick={() => handleChangePage(p)}
                        className={`h-8 w-8 rounded-full text-sm font-medium transition-all duration-200 border ${
                            p === page
                                ? "bg-gradient-to-r from-purple-600 to-indigo-600 text-white border-purple-500 shadow-md shadow-purple-800/50"
                                : "text-gray-200 border-transparent hover:bg-purple-800/40 hover:text-white"
                        }`}
                    >
                        {p}
                    </Button>
                ))}

                <Button
                    size="icon"
                    variant="ghost"
                    disabled={page >= totalPages || loading}
                    onClick={() => handleChangePage(page + 1)}
                    className="hover:bg-purple-700/30 text-gray-200 disabled:opacity-40 rounded-full"
                >
                    <ChevronRight className="h-4 w-4" />
                </Button>

                {loading && (
                    <Loader2 className="ml-2 h-4 w-4 text-purple-400 animate-spin" />
                )}
            </div>
        </div>
    );
}
