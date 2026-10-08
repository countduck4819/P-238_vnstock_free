"use client";

import React from "react";

interface SectorData {
    sector: string;
    stocks: { code: string; change: number }[];
}

const MOCK_HEATMAP: SectorData[] = [
    {
        sector: "Tài chính",
        stocks: [
            { code: "VCB", change: 2.3 },
            { code: "MBB", change: 1.2 },
            { code: "STB", change: 0.8 },
            { code: "TCB", change: -1.5 },
        ],
    },
    {
        sector: "Bất động sản",
        stocks: [
            { code: "VHM", change: 0.7 },
            { code: "NVL", change: -2.9 },
            { code: "PDR", change: 4.1 },
            { code: "DIG", change: 2.7 },
        ],
    },
    {
        sector: "Công nghiệp",
        stocks: [
            { code: "GEX", change: 6.2 },
            { code: "CTD", change: 0.9 },
            { code: "HHV", change: 4.3 },
            { code: "PVT", change: 1.1 },
        ],
    },
];

export default function MarketHeatmap() {
    return (
        <div className="bg-[#101625] rounded-md p-3 overflow-auto">
            <div className="grid grid-cols-3 gap-3 min-h-[20rem]">
                {MOCK_HEATMAP.map((sector) => (
                    <div key={sector.sector} className="flex flex-col gap-2">
                        <div className="text-xs text-gray-300 font-semibold">
                            {sector.sector}
                        </div>
                        <div className="grid grid-cols-2 gap-1 flex-1">
                            {sector.stocks.map((stock) => (
                                <div
                                    key={stock.code}
                                    className={`flex flex-col items-center justify-center text-xs font-medium rounded p-2 transition-all duration-200 ${
                                        stock.change > 0
                                            ? "bg-green-600/70 hover:bg-green-500/80"
                                            : stock.change < 0
                                            ? "bg-red-600/70 hover:bg-red-500/80"
                                            : "bg-yellow-600/60"
                                    }`}
                                >
                                    <div>{stock.code}</div>
                                    <div className="text-[10px]">
                                        {stock.change > 0 ? "+" : ""}
                                        {stock.change}%
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}
