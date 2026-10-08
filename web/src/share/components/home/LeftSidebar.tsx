"use client";

import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import SoftwareTab from "./SoftwareTab";
import InvestmentTab from "./InvestmentTab";
import CKShinhanTab from "./CKShinhanTab";
import { Laptop, TrendingUp, Building2 } from "lucide-react";

const TAB_CONFIG = [
    {
        key: "software",
        label: "Phần mềm",
        icon: Laptop,
        component: SoftwareTab,
    },
    {
        key: "investment",
        label: "Đầu tư",
        icon: TrendingUp,
        component: InvestmentTab,
    },
    {
        key: "ckshinhan",
        label: "CK Shinhan",
        icon: Building2,
        component: CKShinhanTab,
    },
];

export default function LeftSidebar({
    onPickSymbol,
    currentSymbol,
}: {
    onPickSymbol?: (symbol: string) => void;
    currentSymbol?: string;
}) {
    return (
        <Tabs defaultValue="software" className="w-full">
            {/* --- Header Tabs --- */}
            <div className="bg-slate-100/90 dark:bg-slate-900/90 backdrop-blur-md p-1.5 rounded-2xl w-full sm:w-fit border border-slate-200/80 dark:border-slate-800 shadow-sm transition-colors">
                <TabsList className="grid grid-cols-3 sm:flex gap-1 sm:gap-1.5 bg-transparent h-auto p-0 w-full">
                    {TAB_CONFIG.map((tab) => {
                        const Icon = tab.icon;
                        return (
                            <TabsTrigger
                                key={tab.key}
                                value={tab.key}
                                className={[
                                    "flex items-center justify-center gap-1.5 sm:gap-2 px-2.5 sm:px-4 py-2 text-xs md:text-sm font-medium rounded-xl transition-all duration-200 select-none",
                                    "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 hover:bg-white/50 dark:hover:bg-slate-800/50",
                                    "data-[state=active]:bg-white dark:data-[state=active]:bg-slate-800 data-[state=active]:text-indigo-600 dark:data-[state=active]:text-white data-[state=active]:font-semibold data-[state=active]:shadow-sm data-[state=active]:shadow-slate-200/50 dark:data-[state=active]:shadow-none",
                                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500",
                                ].join(" ")}
                            >
                                <Icon className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                                <span className="truncate">{tab.label}</span>
                            </TabsTrigger>
                        );
                    })}
                </TabsList>
            </div>

            {/* --- Tab Content --- */}
            {TAB_CONFIG.map((tab) => {
                const Component = tab.component;
                return (
                    <TabsContent
                        key={tab.key}
                        value={tab.key}
                        className="mt-3 animate-in fade-in-0 slide-in-from-top-1 duration-200"
                    >
                        <Component
                            {...((tab.key === "software"
                                ? { onSelect: onPickSymbol, currentSymbol }
                                : {}) as any)}
                        />
                    </TabsContent>
                );
            })}
        </Tabs>
    );
}
