// "use client";

// import { useState, useEffect } from "react";
// import {
//     Table,
//     TableBody,
//     TableCell,
//     TableHead,
//     TableHeader,
//     TableRow,
// } from "@/components/ui/table";
// import { Loader2, Inbox, Plus } from "lucide-react";
// import { TableSearch } from "./TableSearch";
// import { TablePagination } from "./TablePagination";
// import { Button } from "@/components/ui/button";

// export interface Column<T> {
//     key: keyof T | "actions";
//     header: string;
//     render?: (
//         item: T,
//         actions?: {
//             onEditClick?: (item: T) => void;
//             onDeleteClick?: (item: T) => void;
//         }
//     ) => React.ReactNode;
// }

// interface SearchConfigItem {
//     key: string;
//     label: string;
//     type?: "input" | "select";
//     options?: { label: string; value: string }[];
// }

// interface Meta {
//     page?: number;
//     limit?: number;
//     total?: number;
//     totalPages?: number;
// }

// interface TableCustomProps<T> {
//     columns: Column<T>[];
//     data: T[];
//     meta?: Meta | null;
//     searchConfig?: SearchConfigItem[];
//     loading?: boolean;
//     onAddClick?: () => void;
//     onEditClick?: (item: T) => void;
//     onDeleteClick?: (item: T) => void;
//     onPageChange?: (page: number) => void;
//     onLimitChange?: (limit: number) => void;
//     onFilterChange?: (filters: Record<string, string>) => void;
// }

// export function TableCustom<T>({
//     columns,
//     data,
//     meta,
//     searchConfig,
//     loading = false,
//     onAddClick,
//     onEditClick,
//     onDeleteClick,
//     onPageChange,
//     onLimitChange,
//     onFilterChange,
// }: TableCustomProps<T>) {
//     const [filters, setFilters] = useState<Record<string, string>>({});
//     const [page, setPage] = useState(meta?.page || 1);
//     const [limit, setLimit] = useState(meta?.limit || 10);

//     useEffect(() => {
//         onFilterChange?.(filters);
//     }, [filters]);

//     useEffect(() => {
//         if (onPageChange) onPageChange(page);
//     }, [page]);

//     useEffect(() => {
//         if (onLimitChange) onLimitChange(limit);
//     }, [limit]);

//     return (
//         <div className="space-y-5 relative font-medium">
//             {searchConfig && searchConfig.length > 0 && (
//                 <div className="flex flex-wrap items-end justify-between gap-4">
//                     <div className="flex-1 min-w-[300px]">
//                         <TableSearch
//                             filters={filters}
//                             setFilters={setFilters}
//                             searchConfig={searchConfig}
//                         />
//                     </div>
//                 </div>
//             )}

//             {onAddClick && (
//                 <div className="flex justify-end">
//                     <Button
//                         type="button"
//                         onClick={onAddClick}
//                         className="cursor-pointer bg-gradient-to-r from-[#6A5AF9] to-[#FF5EDF] hover:opacity-90 transition-all duration-200 text-white font-semibold shadow-[0_0_12px_rgba(255,94,223,0.4)] px-5 py-2 rounded-lg flex items-center gap-2"
//                     >
//                         <Plus className="w-4 h-4" />
//                         Thêm mới
//                     </Button>
//                 </div>
//             )}

//             <div className="relative rounded-xl border border-purple-500/30 bg-gradient-to-br from-[#1A1034] via-[#1E153A] to-[#2A1B47] shadow-lg shadow-purple-900/20 overflow-hidden">
//                 {loading && (
//                     <div className="absolute inset-0 bg-gradient-to-br from-purple-900/30 to-indigo-800/30 backdrop-blur-md flex flex-col items-center justify-center z-10 transition-all">
//                         <Loader2 className="h-8 w-8 text-purple-400 animate-spin mb-2" />
//                         <span className="text-sm text-gray-200">
//                             Đang tải dữ liệu...
//                         </span>
//                     </div>
//                 )}

//                 <Table
//                     className={`transition-all duration-200 ${
//                         loading ? "opacity-50 pointer-events-none" : ""
//                     }`}
//                 >
//                     <TableHeader>
//                         <TableRow className="bg-gradient-to-r from-purple-700/80 to-indigo-600/80 border-b border-purple-400/40">
//                             {columns.map((col) => (
//                                 <TableHead
//                                     key={String(col.key)}
//                                     className="text-white font-semibold py-3 px-4 text-sm tracking-wide uppercase"
//                                 >
//                                     {col.header}
//                                 </TableHead>
//                             ))}
//                         </TableRow>
//                     </TableHeader>

//                     <TableBody>
//                         {data?.length ? (
//                             data.map((item, i) => (
//                                 <TableRow
//                                     key={i}
//                                     className={`transition-colors ${
//                                         i % 2 === 0
//                                             ? "bg-[#1C142C]/70"
//                                             : "bg-[#241A3A]/70"
//                                     } hover:bg-purple-700/30`}
//                                 >
//                                     {columns.map((col) => (
//                                         <TableCell
//                                             key={String(col.key)}
//                                             className="text-gray-100 text-sm py-3 px-4"
//                                         >
//                                             {col.render
//                                                 ? col.render(item, {
//                                                       onEditClick,
//                                                       onDeleteClick,
//                                                   })
//                                                 : (item[
//                                                       col.key as keyof T
//                                                   ] as React.ReactNode)}
//                                         </TableCell>
//                                     ))}
//                                 </TableRow>
//                             ))
//                         ) : (
//                             <TableRow>
//                                 <TableCell
//                                     colSpan={columns.length}
//                                     className="text-center py-10 text-gray-400"
//                                 >
//                                     <div className="flex flex-col items-center justify-center">
//                                         <Inbox className="h-10 w-10 text-purple-400 mb-2" />
//                                         <p className="text-sm font-medium">
//                                             Không có dữ liệu để hiển thị
//                                         </p>
//                                     </div>
//                                 </TableCell>
//                             </TableRow>
//                         )}
//                     </TableBody>
//                 </Table>
//             </div>

//             <div className="pt-1">
//                 <TablePagination
//                     page={page}
//                     setPage={setPage}
//                     totalPages={meta?.totalPages || 1}
//                     loading={loading}
//                     limit={limit}
//                     setLimit={setLimit}
//                 />
//             </div>
//         </div>
//     );
// }

"use client";

import { useState, useEffect } from "react";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import { Loader2, Inbox, Plus } from "lucide-react";
import { TableSearch } from "./TableSearch";
import { TablePagination } from "./TablePagination";
import { Button } from "@/components/ui/button";

export interface Column<T> {
    key: keyof T | "actions";
    header: string;
    render?: (
        item: T,
        actions?: {
            onEditClick?: (item: T) => void;
            onDeleteClick?: (item: T) => void;
            onPreview?: (src: string) => void;
        }
    ) => React.ReactNode;
}

interface SearchConfigItem {
    key: string;
    label: string;
    type?: "input" | "select";
    options?: { label: string; value: string }[];
}

interface Meta {
    page?: number;
    limit?: number;
    total?: number;
    totalPages?: number;
}

interface TableCustomProps<T> {
    columns: Column<T>[];
    data: T[];
    meta?: Meta | null;
    searchConfig?: SearchConfigItem[];
    loading?: boolean;
    onAddClick?: () => void;
    onEditClick?: (item: T) => void;
    onDeleteClick?: (item: T) => void;
    onPageChange?: (page: number) => void;
    onLimitChange?: (limit: number) => void;
    onFilterChange?: (filters: Record<string, string>) => void;
}

export function TableCustom<T>({
    columns,
    data,
    meta,
    searchConfig,
    loading = false,
    onAddClick,
    onEditClick,
    onDeleteClick,
    onPageChange,
    onLimitChange,
    onFilterChange,
}: TableCustomProps<T>) {
    const [filters, setFilters] = useState<Record<string, string>>({});
    const [page, setPage] = useState(meta?.page || 1);
    const [limit, setLimit] = useState(meta?.limit || 10);
    const [previewImage, setPreviewImage] = useState<string | null>(null);

    useEffect(() => {
        onFilterChange?.(filters);
    }, [filters]);

    useEffect(() => {
        if (onPageChange) onPageChange(page);
    }, [page]);

    useEffect(() => {
        if (onLimitChange) onLimitChange(limit);
    }, [limit]);

    return (
        <div className="space-y-5 relative font-medium">
            {searchConfig && searchConfig.length > 0 && (
                <div className="flex flex-wrap items-end justify-between gap-4">
                    <div className="flex-1 w-[18.75rem]">
                        <TableSearch
                            filters={filters}
                            setFilters={setFilters}
                            searchConfig={searchConfig}
                        />
                    </div>
                </div>
            )}

            {onAddClick && (
                <div className="flex justify-end">
                    <Button
                        type="button"
                        onClick={onAddClick}
                        className="cursor-pointer bg-gradient-to-r from-[#6A5AF9] to-[#FF5EDF] hover:opacity-90 transition-all duration-200 text-white font-semibold shadow-[0_0_12px_rgba(255,94,223,0.4)] px-5 py-2 rounded-lg flex items-center gap-2"
                    >
                        <Plus className="w-4 h-4" />
                        Thêm mới
                    </Button>
                </div>
            )}

            <div className="relative rounded-xl border border-purple-500/30 bg-gradient-to-br from-[#1A1034] via-[#1E153A] to-[#2A1B47] shadow-lg shadow-purple-900/20 overflow-hidden">
                {loading && (
                    <div className="absolute inset-0 bg-gradient-to-br from-purple-900/30 to-indigo-800/30 backdrop-blur-md flex flex-col items-center justify-center z-10 transition-all">
                        <Loader2 className="h-8 w-8 text-purple-400 animate-spin mb-2" />
                        <span className="text-sm text-gray-200">
                            Đang tải dữ liệu...
                        </span>
                    </div>
                )}

                <Table
                    className={`transition-all duration-200 ${
                        loading ? "opacity-50 pointer-events-none" : ""
                    }`}
                >
                    <TableHeader>
                        <TableRow className="bg-gradient-to-r from-purple-700/80 to-indigo-600/80 border-b border-purple-400/40">
                            {columns.map((col) => (
                                <TableHead
                                    key={String(col.key)}
                                    className="text-white font-semibold py-3 px-4 text-sm tracking-wide uppercase"
                                >
                                    {col.header}
                                </TableHead>
                            ))}
                        </TableRow>
                    </TableHeader>

                    <TableBody>
                        {data?.length ? (
                            data.map((item, i) => (
                                <TableRow
                                    key={i}
                                    className={`transition-colors ${
                                        i % 2 === 0
                                            ? "bg-[#1C142C]/70"
                                            : "bg-[#241A3A]/70"
                                    } hover:bg-purple-700/30`}
                                >
                                    {columns.map((col) => (
                                        <TableCell
                                            key={String(col.key)}
                                            className="text-gray-100 text-sm py-3 px-4"
                                        >
                                            {col.render
                                                ? col.render(item, {
                                                      onEditClick,
                                                      onDeleteClick,
                                                      onPreview: (src) =>
                                                          setPreviewImage(src), // ⭐ THÊM
                                                  })
                                                : (item[
                                                      col.key as keyof T
                                                  ] as React.ReactNode)}
                                        </TableCell>
                                    ))}
                                </TableRow>
                            ))
                        ) : (
                            <TableRow>
                                <TableCell
                                    colSpan={columns.length}
                                    className="text-center py-10 text-gray-400"
                                >
                                    <div className="flex flex-col items-center justify-center">
                                        <Inbox className="h-10 w-10 text-purple-400 mb-2" />
                                        <p className="text-sm font-medium">
                                            Không có dữ liệu để hiển thị
                                        </p>
                                    </div>
                                </TableCell>
                            </TableRow>
                        )}
                    </TableBody>
                </Table>
            </div>

            <div className="pt-1">
                <TablePagination
                    page={page}
                    setPage={setPage}
                    totalPages={meta?.totalPages || 1}
                    loading={loading}
                    limit={limit}
                    setLimit={setLimit}
                />
            </div>

            {previewImage && (
                <div
                    onClick={() => setPreviewImage(null)}
                    className="fixed inset-0 bg-black/70 flex items-center justify-center z-[999]"
                >
                    <div className="relative w-[80%] h-[80%] bg-black rounded-lg overflow-hidden">
                        <img
                            src={previewImage}
                            alt="preview"
                            className="w-full h-full object-contain"
                        />
                    </div>
                </div>
            )}
        </div>
    );
}
