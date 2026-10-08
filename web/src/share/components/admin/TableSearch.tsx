"use client";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { Search } from "lucide-react";
import { useState, useEffect } from "react";

interface SearchConfigItem {
    key: string;
    label: string;
    type?: "input" | "select";
    options?: { label: string; value: string }[];
}

interface TableSearchProps {
    filters: Record<string, string>;
    setFilters: React.Dispatch<React.SetStateAction<Record<string, string>>>;
    searchConfig?: SearchConfigItem[];
}

export function TableSearch({
    filters,
    setFilters,
    searchConfig = [],
}: TableSearchProps) {
    const [localFilters, setLocalFilters] =
        useState<Record<string, string>>(filters);

    useEffect(() => {
        const timer = setTimeout(() => {
            setFilters(localFilters);
        }, 400);
        return () => clearTimeout(timer);
    }, [localFilters]);

    const handleChange = (key: string, value: string) => {
        setLocalFilters((prev) => ({ ...prev, [key]: value }));
    };

    return (
        <form
            autoComplete="off"
            className="flex flex-wrap gap-4 items-end justify-start 
        bg-gradient-to-r from-[#1A1032] to-[#231A42] 
        p-4 rounded-xl border border-purple-600/20 
        shadow-[0_0_1.5rem_rgba(139,92,246,0.15)] backdrop-blur-md"
        >
            <input
                type="text"
                name="fake-username"
                autoComplete="username"
                hidden
            />
            <input
                type="password"
                name="fake-password"
                autoComplete="new-password"
                hidden
            />

            {searchConfig.map((item) => (
                <div key={item.key} className="flex flex-col gap-1 w-[13.75rem]">
                    <Label className="text-gray-200 text-sm font-medium">
                        {item.label}
                    </Label>

                    {item.type === "select" && item.options ? (
                        <Select
                            value={localFilters[item.key] ?? ""}
                            onValueChange={(v) => handleChange(item.key, v)}
                        >
                            <SelectTrigger
                                className="relative bg-[#201738]/90 text-gray-100 border border-purple-500/30
                hover:border-purple-400/60 focus:ring-2 focus:ring-purple-600/40
                rounded-lg transition-all shadow-sm"
                            >
                                <SelectValue placeholder="Chọn..." />
                            </SelectTrigger>
                            <SelectContent
                                className="bg-[#1E1538]/95 border border-purple-600/40 
                text-gray-100 shadow-xl backdrop-blur-md"
                            >
                                {item.options.map((opt) => (
                                    <SelectItem
                                        key={opt.value}
                                        value={opt.value}
                                        className="hover:bg-purple-700/25 cursor-pointer text-gray-200"
                                    >
                                        {opt.label}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    ) : (
                        <div className="relative">
                            <Search className="absolute left-2 top-2.5 h-4 w-4 text-purple-400/70" />
                            <Input
                                name={`filter-${item.key}`}
                                autoComplete="off"
                                placeholder={item.label}
                                value={localFilters[item.key] ?? ""}
                                onChange={(e) =>
                                    handleChange(item.key, e.target.value)
                                }
                                className="pl-8 bg-[#201738]/90 text-gray-100
                border border-purple-500/30 hover:border-purple-400/60
                focus:ring-2 focus:ring-purple-600/40 focus:border-purple-400
                placeholder:text-gray-400 transition-all rounded-lg shadow-sm"
                            />
                        </div>
                    )}
                </div>
            ))}
        </form>
    );
}
