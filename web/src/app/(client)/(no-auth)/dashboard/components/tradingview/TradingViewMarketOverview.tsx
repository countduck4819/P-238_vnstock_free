"use client";

import { useEffect, useRef } from "react";

export default function TradingViewMarketOverview() {
    const container = useRef<HTMLDivElement | null>(null);

    useEffect(() => {
        if (!container.current) return;

        const script = document.createElement("script");
        script.src =
            "https://s3.tradingview.com/external-embedding/embed-widget-market-overview.js";
        script.async = true;
        script.innerHTML = JSON.stringify({
            colorTheme: "dark",
            dateRange: "1D",
            showChart: true,
            locale: "vi_VN",
            largeChartUrl: "",
            isTransparent: false,
            showSymbolLogo: true,
            width: "100%",
            height: "100%",
            plotLineColorGrowing: "rgba(41, 98, 255, 1)",
            plotLineColorFalling: "rgba(255, 0, 0, 1)",
            gridLineColor: "rgba(240, 243, 250, 0)",
            scaleFontColor: "rgba(106, 109, 120, 1)",
            belowLineFillColorGrowing: "rgba(41, 98, 255, 0.12)",
            belowLineFillColorFalling: "rgba(255, 0, 0, 0.12)",
            tabs: [
                {
                    title: "Chỉ số chính",
                    symbols: [
                        { s: "INDEX:VNINDEX", d: "VNINDEX" },
                        { s: "HNX:HNXINDEX", d: "HNXINDEX" },
                        { s: "HNX:UPCOM", d: "UPCOM" },
                        { s: "HNX:VN30", d: "VN30" },
                    ],
                },
                {
                    title: "Ngân hàng",
                    symbols: [
                        { s: "HOSE:TCB", d: "Techcombank" },
                        { s: "HOSE:VCB", d: "Vietcombank" },
                        { s: "HOSE:MBB", d: "MB Bank" },
                        { s: "HOSE:STB", d: "Sacombank" },
                    ],
                },
                {
                    title: "Bất động sản",
                    symbols: [
                        { s: "HOSE:NVL", d: "Novaland" },
                        { s: "HOSE:VHM", d: "Vinhomes" },
                        { s: "HOSE:KDH", d: "Khang Điền" },
                        { s: "HOSE:PDR", d: "Phát Đạt" },
                    ],
                },
            ],
        });

        container.current.appendChild(script);

        return () => {
            while (container.current?.firstChild) {
                container.current.removeChild(container.current.firstChild);
            }
        };
    }, []);

    return (
        <div className="w-full h-full bg-[#101625] rounded-md overflow-hidden">
            <div className="tradingview-widget-container" ref={container}></div>
        </div>
    );
}
