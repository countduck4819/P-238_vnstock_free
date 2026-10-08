"use client";

import {
    useEffect,
    useMemo,
} from "react";

import type { ReactNode } from "react";

import { useParams } from "next/navigation";

import {
    useAppDispatch,
    useAppSelector,
} from "@/redux/hooks";

import { fetchFinanceIndex } from "@/store/finance-index/finance-index.api";

import type { FinanceRecord } from "@/store/finance-index/finance-index.reducer";

import { StockIndex } from "../enum";


type StockInfoCardProps = {
    symbol?: string;
};


export default function StockInfoCard({
    symbol,
}: StockInfoCardProps) {
    const params = useParams();

    const dispatch = useAppDispatch();

    const {
        data,
        symbol: financeSymbol,
        partial: financePartial,
    } = useAppSelector(
        (state) => state.financeIndex
    );

    const {
        candleData,
    } = useAppSelector(
        (state) => state.stockSymbols
    );

    const stock = (
        symbol ||
        String(params.stock || "")
    )
        .trim()
        .toUpperCase();

    useEffect(() => {
        if (!stock) {
            return;
        }

        // VNINDEX không cần financial ratio
        if (stock === StockIndex.VNINDEX) {
            return;
        }

        const request = dispatch(
            fetchFinanceIndex(stock)
        );

        return () => {
            request.abort();
        };
    }, [
        stock,
        dispatch,
    ]);

    // Market.summary trả các số Tổng quan chính rất nhanh. Fundamental.ratio
    // tiếp tục hoàn thiện cache nền; poll nhẹ để EPS/Beta tự hiện mà không bắt
    // request đầu tiên phải đứng chờ toàn bộ ratio.
    useEffect(() => {
        if (
            !stock ||
            stock === StockIndex.VNINDEX ||
            financeSymbol !== stock ||
            !financePartial
        ) {
            return;
        }

        let cancelled = false;
        let attempts = 0;
        let abortActiveRequest: (() => void) | null = null;

        const timer = setInterval(async () => {
            if (cancelled || attempts >= 4) {
                clearInterval(timer);
                return;
            }

            attempts += 1;
            const request = dispatch(
                fetchFinanceIndex(stock)
            );
            abortActiveRequest = () => request.abort();

            try {
                const payload = await request.unwrap();

                if (!payload?.partial) {
                    clearInterval(timer);
                }
            } catch {
                // Background ratio có thể chưa xong; lượt sau thử lại.
            } finally {
                abortActiveRequest = null;
            }
        }, 4000);

        return () => {
            cancelled = true;
            clearInterval(timer);
            abortActiveRequest?.();
        };
    }, [
        stock,
        financeSymbol,
        financePartial,
        dispatch,
    ]);

    /**
     * Không dùng data cũ nếu user vừa chuyển
     * từ mã khác sang.
     */
    const financeData = useMemo(
        () => {
            if (
                financeSymbol &&
                financeSymbol !== stock
            ) {
                return [];
            }

            return data || [];
        },
        [
            data,
            financeSymbol,
            stock,
        ]
    );

    // =====================================================
    // PRICE DATA
    // =====================================================

    const last = candleData.at(-1);

    const prev = candleData.at(-2);

    const reference =
        Number(prev?.close) || 0;

    const open =
        Number(last?.open) || 0;

    const low =
        Number(last?.low) || 0;

    const high =
        Number(last?.high) || 0;

    const volume =
        Number(last?.volume) || 0;

    /**
     * Giá VN thường đang ở đơn vị:
     *
     * 24.95 = 24,950 VNĐ
     *
     * Vì vậy cần * 1000 trước khi đổi sang tỷ.
     */
    const value =
        (
            volume *
            open *
            1000
        ) /
        1_000_000_000;

    // =====================================================
    // AVERAGE VOLUME 10 DAYS
    // =====================================================

    const avgVolume10 = useMemo(
        () => {
            if (
                !Array.isArray(candleData) ||
                candleData.length === 0
            ) {
                return null;
            }

            const last10 =
                candleData.slice(-10);

            const validVolumes =
                last10
                    .map(
                        (item) =>
                            Number(
                                item?.volume
                            )
                    )
                    .filter(
                        (item) =>
                            Number.isFinite(
                                item
                            ) &&
                            item >= 0
                    );

            if (
                validVolumes.length === 0
            ) {
                return null;
            }

            const total =
                validVolumes.reduce(
                    (
                        sum,
                        current
                    ) =>
                        sum +
                        current,
                    0
                );

            return (
                total /
                validVolumes.length
            );
        },
        [candleData]
    );

    // =====================================================
    // HELPERS
    // =====================================================

    const isValidNumber = (
        val: unknown
    ) => {
        if (
            val === null ||
            val === undefined ||
            val === ""
        ) {
            return false;
        }

        const number =
            Number(val);

        return Number.isFinite(
            number
        );
    };

    /**
     * Backend đã sort kỳ mới nhất trước.
     */
    const findMetricById = (
        ids: string | string[]
    ): FinanceRecord | null => {
        const normalizedIds = (
            Array.isArray(ids) ? ids : [ids]
        ).map((id) => id.toUpperCase());

        const row = financeData.find(
            (item) =>
                normalizedIds.includes(
                    String(
                        item?.id ||
                        item?.source_id ||
                        ""
                    ).toUpperCase()
                ) &&
                isValidNumber(
                    item?.value
                )
        );

        return row || null;
    };

    const findMetricByText = (
        keywords: string[]
    ): FinanceRecord | null => {
        const normalizedKeywords =
            keywords.map(
                (keyword) =>
                    keyword
                        .trim()
                        .toUpperCase()
            );

        const row = financeData.find(
            (item) => {
                if (
                    !isValidNumber(
                        item?.value
                    )
                ) {
                    return false;
                }

                const id = String(
                    item?.id || ""
                ).toUpperCase();

                const name = String(
                    item?.name || ""
                ).toUpperCase();

                return normalizedKeywords.every(
                    (keyword) =>
                        id.includes(
                            keyword
                        ) ||
                        name.includes(
                            keyword
                        )
                );
            }
        );

        return row || null;
    };

    const metricValue = (
        metric:
            | FinanceRecord
            | null
    ) => {
        if (
            !metric ||
            !isValidNumber(
                metric.value
            )
        ) {
            return null;
        }

        return Number(
            metric.value
        );
    };

    const formatNum = (
        val: unknown,
        digits = 2
    ) => {
        if (
            val === null ||
            val === undefined ||
            val === ""
        ) {
            return "-";
        }

        const num =
            Number(val);

        if (
            !Number.isFinite(num)
        ) {
            return "-";
        }

        const abs =
            Math.abs(num);

        if (
            abs >=
            1_000_000_000_000
        ) {
            return (
                (
                    num /
                    1_000_000_000_000
                ).toLocaleString(
                    "vi-VN",
                    {
                        maximumFractionDigits:
                            digits,
                    }
                ) +
                " nghìn tỷ"
            );
        }

        if (
            abs >=
            1_000_000_000
        ) {
            return (
                (
                    num /
                    1_000_000_000
                ).toLocaleString(
                    "vi-VN",
                    {
                        maximumFractionDigits:
                            digits,
                    }
                ) +
                " tỷ"
            );
        }

        if (
            abs >=
            1_000_000
        ) {
            return (
                (
                    num /
                    1_000_000
                ).toLocaleString(
                    "vi-VN",
                    {
                        maximumFractionDigits:
                            digits,
                    }
                ) +
                " tr"
            );
        }

        return num.toLocaleString(
            "vi-VN",
            {
                maximumFractionDigits:
                    digits,
            }
        );
    };

    const colored = (
        val: unknown,
        {
            positive = "text-green-600 dark:text-emerald-400",
            negative = "text-red-500 dark:text-rose-400",
        } = {}
    ) => {
        if (
            !isValidNumber(val)
        ) {
            return "text-gray-800 dark:text-slate-200";
        }

        const num =
            Number(val);

        if (num > 0) {
            return `${positive} font-semibold`;
        }

        if (num < 0) {
            return `${negative} font-semibold`;
        }

        return "text-gray-800 dark:text-slate-200";
    };

    const priceColor = (
        price: number
    ) => {
        if (
            !reference ||
            !price
        ) {
            return "text-gray-800 dark:text-slate-200";
        }

        if (
            price > reference
        ) {
            return "text-green-600 dark:text-emerald-400";
        }

        if (
            price < reference
        ) {
            return "text-red-500 dark:text-rose-400";
        }

        return "text-amber-500 dark:text-amber-400";
    };

    // =====================================================
    // FINANCIAL METRICS
    // =====================================================

    const peMetric =
        findMetricById(
            [
                "RT_VALUE_PE",
                "p_e",
                "pe",
                "price_to_earning",
            ]
        ) || findMetricByText(["P/E"]);

    const pe =
        metricValue(
            peMetric
        );

    const epsMetric =
        findMetricById(
            [
                "RT_VALUE_EPS",
                "trailing_eps",
                "eps",
            ]
        ) || findMetricByText(["EPS"]);

    let eps =
        metricValue(
            epsMetric
        );

    let epsEstimated = false;

    if (
        eps === null &&
        pe !== null &&
        pe !== 0 &&
        reference > 0
    ) {
        eps = (reference * 1000) / pe;
        epsEstimated = true;
    }

    const betaMetric =
        findMetricById(
            [
                "RT_VALUE_BETA",
                "beta",
            ]
        ) || findMetricByText(["BETA"]);

    const beta =
        metricValue(
            betaMetric
        );

    const marketCapMetric =
        findMetricById(
            [
                "RT_VALUE_MARKET_CAP",
                "market_cap",
                "market_capital",
                "market_capitalization",
            ]
        ) || findMetricByText([
            "MARKET",
            "CAP",
        ]);

    const marketCap =
        metricValue(
            marketCapMetric
        );

    // =====================================================
    // OUTSTANDING SHARES
    // =====================================================

    const outstandingSharesMetric =
        findMetricById([
            "RT_VALUE_OUTSTANDING_SHARES",
            "outstanding_share",
            "outstanding_shares",
        ]) || findMetricByText([
            "OUTSTANDING",
            "SHARE",
        ]);

    let outstandingShares =
        metricValue(
            outstandingSharesMetric
        );

    let outstandingEstimated =
        false;

    if (
        outstandingShares !==
            null &&
        outstandingSharesMetric
    ) {
        const unit = String(
            outstandingSharesMetric
                .unit || ""
        ).toLowerCase();

        if (
            unit.includes("mil") ||
            unit.includes(
                "million"
            ) ||
            unit.includes(
                "triệu"
            )
        ) {
            outstandingShares *=
                1_000_000;
        }
    }

    if (
        outstandingShares ===
            null &&
        marketCap !== null &&
        reference > 0
    ) {
        outstandingShares =
            marketCap /
            (
                reference *
                1000
            );

        outstandingEstimated =
            true;
    }

    // =====================================================
    // UI
    // =====================================================

    return (
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-sm overflow-hidden text-sm transition-colors">
            {/* Header */}
            <div className="flex border-b border-slate-200 dark:border-slate-800 bg-[#F5F9FF] dark:bg-slate-800/70 items-center justify-between px-4 py-3">
                <div className="font-bold text-[0.95rem] text-blue-900 dark:text-blue-300">
                    Tổng quan
                </div>

                <div className="text-xs text-gray-500 dark:text-slate-400 font-semibold font-mono">
                    {stock || "-"}
                </div>
            </div>

            {/* Body */}
            <div className="divide-y divide-gray-100 dark:divide-slate-800/80 p-4">
                <Row
                    label="Tham chiếu"
                    value={
                        <span className="text-amber-500 dark:text-amber-400 font-bold">
                            {reference
                                ? reference.toFixed(
                                      2
                                  )
                                : "-"}
                        </span>
                    }
                />

                <Row
                    label="Mở cửa"
                    value={
                        <span
                            className={priceColor(
                                open
                            )}
                        >
                            {open
                                ? open.toFixed(
                                      2
                                  )
                                : "-"}
                        </span>
                    }
                />

                <Row
                    label="Thấp - Cao"
                    value={
                        low || high ? (
                            <span className="font-semibold">
                                <span
                                    className={priceColor(
                                        low
                                    )}
                                >
                                    {low
                                        ? low.toFixed(
                                              2
                                          )
                                        : "-"}
                                </span>

                                {" - "}

                                <span
                                    className={priceColor(
                                        high
                                    )}
                                >
                                    {high
                                        ? high.toFixed(
                                              2
                                          )
                                        : "-"}
                                </span>
                            </span>
                        ) : (
                            "-"
                        )
                    }
                />

                <Row
                    label="Khối lượng"
                    value={
                        volume
                            ? volume.toLocaleString(
                                  "vi-VN"
                              )
                            : "-"
                    }
                />

                <Row
                    label="Giá trị"
                    value={
                        volume &&
                        open
                            ? `${value.toLocaleString(
                                  "vi-VN",
                                  {
                                      maximumFractionDigits:
                                          2,
                                  }
                              )} tỷ`
                            : "-"
                    }
                />

                {stock !==
                    StockIndex.VNINDEX && (
                    <>
                        <Row
                            label="KLTB 10 ngày"
                            value={
                                avgVolume10 !==
                                null
                                    ? Math.round(
                                          avgVolume10
                                      ).toLocaleString(
                                          "vi-VN"
                                      )
                                    : "-"
                            }
                        />

                        <Row
                            label="Beta"
                            value={
                                beta !==
                                null ? (
                                    <span
                                        className={colored(
                                            beta
                                        )}
                                    >
                                        {formatNum(
                                            beta,
                                            2
                                        )}
                                    </span>
                                ) : (
                                    "-"
                                )
                            }
                        />

                        <Row
                            label="Thị giá vốn"
                            value={
                                marketCap !==
                                null
                                    ? formatNum(
                                          marketCap,
                                          2
                                      )
                                    : "-"
                            }
                        />

                        <Row
                            label="Số lượng CPHL"
                            value={
                                outstandingShares !==
                                null
                                    ? `${
                                          outstandingEstimated
                                              ? "~"
                                              : ""
                                      }${formatNum(
                                          outstandingShares,
                                          2
                                      )}`
                                    : "-"
                            }
                        />

                        <Row
                            label="P/E"
                            value={
                                pe !==
                                null ? (
                                    <span
                                        className={colored(
                                            pe
                                        )}
                                    >
                                        {formatNum(
                                            pe,
                                            2
                                        )}
                                    </span>
                                ) : (
                                    "-"
                                )
                            }
                        />

                        <Row
                            label="EPS"
                            value={
                                eps !==
                                null ? (
                                    <span
                                        className={colored(
                                            eps
                                        )}
                                    >
                                        {epsEstimated ? "~" : ""}
                                        {formatNum(eps, 2)}
                                    </span>
                                ) : (
                                    "-"
                                )
                            }
                        />
                    </>
                )}
            </div>
        </div>
    );
}


function Row({
    label,
    value,
}: {
    label: string;
    value:
        | string
        | number
        | ReactNode;
}) {
    return (
        <div className="flex justify-between py-1.5 gap-4 text-xs">
            <span className="text-slate-500 dark:text-slate-400 shrink-0">
                {label}
            </span>

            <span className="text-right font-medium min-w-0 text-slate-900 dark:text-slate-200">
                {value}
            </span>
        </div>
    );
}
