"use client";

import { useEffect, useState, useMemo, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { Search } from "lucide-react";

import { useAppDispatch, useAppSelector } from "@/redux/hooks";
import { fetchStocks } from "@/store/stock-symbols/stock-symbols.api";

import { Input } from "@/components/ui/input";

function removeVietnameseTones(str: string): string {
    return str
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/đ/g, "d")
        .replace(/Đ/g, "D")
        .toLowerCase()
        .trim();
}

export default function SearchBox() {
    const router = useRouter();
    const dispatch = useAppDispatch();

    const { stocksFullList, loading } = useAppSelector(
        (state) => state.stockSymbols,
    );

    const [open, setOpen] = useState(false);
    const [value, setValue] = useState("");
    const [history, setHistory] = useState<string[]>([]);

    const boxRef = useRef<HTMLDivElement>(null);

    // bắt outside click
    useEffect(() => {
        function handleClickOutside(e: any) {
            if (boxRef.current && !boxRef.current.contains(e.target)) {
                setOpen(false);
            }
        }
        document.addEventListener("mousedown", handleClickOutside);
        return () =>
            document.removeEventListener("mousedown", handleClickOutside);
    }, []);

    useEffect(() => {
        if (!stocksFullList?.length) dispatch(fetchStocks());
        const saved = JSON.parse(
            localStorage.getItem("search-history") || "[]",
        );
        if (Array.isArray(saved)) setHistory(saved);
    }, [dispatch, stocksFullList?.length]);

    const filtered = useMemo(() => {
        const term = value.trim();
        const termLower = term.toLowerCase();
        const termNorm = removeVietnameseTones(term);

        // Khử trùng lặp stocksFullList và chuẩn hóa dữ liệu
        const uniqueStocksMap = new Map<string, { symbol: string; org_name: string }>();
        for (const item of stocksFullList || []) {
            if (!item?.symbol) continue;
            const sym = String(item.symbol).toUpperCase().trim();
            const existing = uniqueStocksMap.get(sym);
            const name = String(item.org_name || (item as any)?.organ_name || "").trim();
            // Ưu tiên bản ghi có tên công ty thực tế (khác với mã symbol)
            if (
                !existing ||
                (!existing.org_name && name) ||
                (existing.org_name === sym && name && name !== sym)
            ) {
                uniqueStocksMap.set(sym, {
                    symbol: sym,
                    org_name: name || sym,
                });
            }
        }

        if (term === "") {
            const seenHistory = new Set<string>();
            const list = [];
            for (const code of history) {
                const upper = String(code).toUpperCase().trim();
                if (!seenHistory.has(upper)) {
                    seenHistory.add(upper);
                    const found = uniqueStocksMap.get(upper) || stocksFullList.find((s) => s.symbol?.toUpperCase() === upper);
                    if (found) list.push(found);
                }
                if (list.length >= 10) break;
            }
            return list;
        }

        interface ScoredItem {
            item: { symbol: string; org_name: string };
            score: number;
        }

        const scored: ScoredItem[] = [];

        for (const item of uniqueStocksMap.values()) {
            const symLower = item.symbol.toLowerCase();
            const symNorm = removeVietnameseTones(item.symbol);
            const nameLower = (item.org_name || "").toLowerCase();
            const nameNorm = removeVietnameseTones(item.org_name || "");

            let score = -1;

            if (symLower === termLower || symNorm === termNorm) {
                // 1. Khớp chính xác mã cổ phiếu -> Ưu tiên cao nhất
                score = 1000;
            } else if (symLower.startsWith(termLower) || symNorm.startsWith(termNorm)) {
                // 2. Mã bắt đầu bằng từ khóa (ví dụ gõ 'ld' -> 'LDG')
                score = 500 - symLower.length;
            } else if (symLower.includes(termLower) || symNorm.includes(termNorm)) {
                // 3. Mã chứa từ khóa
                score = 300;
            } else if (nameLower.startsWith(termLower) || nameNorm.startsWith(termNorm)) {
                // 4. Tên công ty bắt đầu bằng từ khóa
                score = 200;
            } else {
                // 5. Kiểm tra các từ trong tên công ty
                const words = nameNorm.split(/\s+/);
                if (words.some((w) => w.startsWith(termNorm))) {
                    score = 150;
                } else if (nameLower.includes(termLower) || nameNorm.includes(termNorm)) {
                    score = 100;
                }
            }

            if (score > 0) {
                scored.push({ item, score });
            }
        }

        scored.sort((a, b) => {
            if (b.score !== a.score) return b.score - a.score;
            return a.item.symbol.localeCompare(b.item.symbol);
        });

        return scored.slice(0, 30).map((s) => s.item);
    }, [value, stocksFullList, history]);

    const handleSelect = useCallback(
        (code: string) => {
            const cleanCode = code.toUpperCase().trim();
            const updated = [cleanCode, ...history.filter((i) => i.toUpperCase().trim() !== cleanCode)].slice(
                0,
                10,
            );
            localStorage.setItem("search-history", JSON.stringify(updated));
            setHistory(updated);
            setOpen(false);
            setValue("");
            router.push(`/ma-chung-khoan/${cleanCode}`);
        },
        [history, router],
    );

    const hasTerm = Boolean(value.trim());

    return (
        <div ref={boxRef} className="relative w-full max-w-[20rem]">
            <Input
                value={value}
                onChange={(e) => {
                    setValue(e.target.value);
                    setOpen(true);
                }}
                onFocus={() => setOpen(true)}
                placeholder="Nhập mã hoặc tên công ty..."
                className="pr-8 bg-white/90 dark:bg-slate-900 border-slate-200 dark:border-slate-800 text-slate-900 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 rounded-xl"
                autoComplete="off"
            />
            <Search className="absolute right-2.5 top-1/2 size-4 -translate-y-1/2 text-slate-400 dark:text-slate-500 pointer-events-none" />

            {/* Drop-down */}
            {open && (
                <div className="absolute mt-2 left-0 z-50 w-full p-0 rounded-xl shadow-xl overflow-hidden bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-slate-100">
                    <div className="border-b border-slate-100 dark:border-slate-800 px-3.5 py-2 font-semibold text-xs text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-950/60">
                        {hasTerm ? "Kết quả tìm kiếm" : "Mã gần đây"}
                    </div>

                    <div className="max-h-[300px] overflow-auto">
                        {loading ? (
                            <div className="px-3.5 py-3 text-xs text-slate-500 dark:text-slate-400">
                                Đang tải danh sách...
                            </div>
                        ) : filtered.length === 0 ? (
                            <div className="px-3.5 py-3 text-xs text-slate-500 dark:text-slate-400">
                                {hasTerm
                                    ? "Không tìm thấy mã phù hợp"
                                    : "Chưa có lịch sử tìm kiếm"}
                            </div>
                        ) : (
                            filtered.map((item) =>
                                item ? (
                                    <button
                                        key={item.symbol}
                                        onClick={() =>
                                            handleSelect(item.symbol)
                                        }
                                        className="w-full text-left px-3.5 py-2.5 hover:bg-blue-50 dark:hover:bg-slate-800 active:bg-blue-100 dark:active:bg-slate-700/80 focus:outline-none transition-colors border-b border-slate-100/60 dark:border-slate-800/60 last:border-0"
                                    >
                                        <div className="font-bold text-sm text-slate-900 dark:text-white">
                                            {item.symbol}
                                        </div>
                                        <div className="text-xs text-slate-500 dark:text-slate-400 truncate">
                                            {item.org_name || (item as any)?.organ_name}
                                        </div>
                                    </button>
                                ) : null,
                            )
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
