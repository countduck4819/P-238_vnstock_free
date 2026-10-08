"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { useDispatch } from "react-redux";
import { useParams, useRouter } from "next/navigation";
import { MessageSquare, Repeat2, ThumbsUp } from "lucide-react";

import { AppDispatch, RootState } from "@/redux/store";

import { useAppSelector } from "@/redux/hooks";

import {
    fetchNewsFromJson,
    fetchNewsQuery,
    fetchAllNewsForVNINDEX,
} from "@/store/news/news.api";

import { api } from "@/utils/axiosInstance";
import { StockIndex } from "../enum";

function formatDate(dateStr?: string) {
    if (!dateStr) return "";

    const date = new Date(dateStr);

    if (isNaN(date.getTime())) {
        return "";
    }

    const day = String(date.getDate()).padStart(2, "0");

    const month = String(date.getMonth() + 1).padStart(2, "0");

    const hours = String(date.getHours()).padStart(2, "0");

    const minutes = String(date.getMinutes()).padStart(2, "0");

    return `${day}/${month} ${hours}:${minutes}`;
}

export default function NewsListJson() {
    const router = useRouter();

    const dispatch = useDispatch<AppDispatch>();

    const {
        currentSymbol,

        list,
        meta,

        vnindexList,
        vnindexMeta,

        error,
    } = useAppSelector((state: RootState) => state.news);

    const { candleData } = useAppSelector(
        (state: RootState) => state.stockSymbols,
    );

    const params = useParams();

    const symbol = String(params.stock || "")
        .toUpperCase()
        .trim();

    const limit = 10;

    const isVNINDEX = symbol === StockIndex?.VNINDEX;

    const [page, setPage] = useState(1);

    const [isFetchingMore, setIsFetchingMore] = useState(false);

    const isFetchingMoreRef = useRef(false);
    const loadMoreTriggerRef = useRef<HTMLDivElement | null>(null);

    const [isPreparingNews, setIsPreparingNews] = useState(false);

    // =====================================================
    // LOAD NEWS
    //
    // Mã thường:
    //
    // Python
    //   ↓
    // import NestJS
    //   ↓
    // DB page 1
    //
    // Gộp thành 1 flow để tránh jsonData mã cũ
    // trigger import cho mã mới.
    // =====================================================

    useEffect(() => {
        if (!symbol) {
            return;
        }

        let cancelled = false;

        setPage(1);
        isFetchingMoreRef.current = false;
        setIsFetchingMore(false);

        // =========================
        // VNINDEX
        // =========================

        if (isVNINDEX) {
            setIsPreparingNews(false);

            dispatch(
                fetchAllNewsForVNINDEX({
                    page: 1,
                    limit,
                }),
            );

            return () => {
                cancelled = true;
            };
        }

        // =========================
        // STOCK
        // =========================

        setIsPreparingNews(true);

        // Hiển thị dữ liệu đã có trong DB ngay. Không bắt giao diện phải chờ
        // Python gọi vnstock_data xong rồi mới được tải page 1.
        const initialDbRequest = dispatch(
            fetchNewsQuery({
                symbol,
                page: 1,
                limit,
            }),
        );

        const syncController = new AbortController();

        let activePythonRequest: {
            abort: () => void;
            unwrap: () => Promise<unknown>;
        } | null = null;

        let refreshDbRequest: {
            abort: () => void;
            unwrap: () => Promise<unknown>;
        } | null = null;

        const sleep = (ms: number) =>
            new Promise<void>((resolve) => {
                setTimeout(resolve, ms);
            });

        const shouldRetry = (err: any) => {
            const status =
                err?.status ?? err?.response?.status ?? err?.originalStatus;

            const code =
                err?.code ?? err?.data?.code ?? err?.response?.data?.code;

            const message = String(
                err?.message ?? err?.data?.message ?? err?.data?.error ?? "",
            );

            return (
                status === 503 ||
                status === 504 ||
                code === "NEWS_UPSTREAM_TIMEOUT" ||
                code === "NEWS_UPSTREAM_UNAVAILABLE" ||
                message.includes("quá thời gian") ||
                message.includes("UPSTREAM_TIMEOUT")
            );
        };

        const preparePythonNews = async () => {
            const maxAttempts = 20;
            const retryDelay = 3000;

            for (let attempt = 1; attempt <= maxAttempts; attempt++) {
                if (cancelled) {
                    return false;
                }

                try {
                    const request = dispatch(fetchNewsFromJson(symbol));

                    activePythonRequest = request;

                    await request.unwrap();

                    console.log(`✅ Python news ${symbol} đã sẵn sàng`);

                    return true;
                } catch (err: unknown) {
                    if (cancelled) {
                        return false;
                    }

                    if (!shouldRetry(err)) {
                        throw err;
                    }

                    console.log(
                        `⏳ News ${symbol} chưa sẵn sàng ` +
                            `(lần ${attempt}/${maxAttempts})`,
                    );

                    if (attempt === maxAttempts) {
                        throw err;
                    }

                    await sleep(retryDelay);
                }
            }

            return false;
        };

        const loadNews = async () => {
            try {
                // Python có thể timeout ở request đầu,
                // nhưng worker backend vẫn tiếp tục chạy.
                //
                // Frontend retry đến khi cache sẵn sàng.
                const ready = await preparePythonNews();

                if (!ready || cancelled) {
                    return;
                }

                // Cache Python đã có
                // → import JSON vào NestJS DB
                await api.post(
                    `/news/import/${symbol}`,
                    {
                        page: 1,
                        limit,
                    },
                    {
                        signal: syncController.signal,
                    },
                );

                if (cancelled) {
                    return;
                }

                // Import xong
                // → lấy page 1 mới từ DB
                const request = dispatch(
                    fetchNewsQuery({
                        symbol,
                        page: 1,
                        limit,
                    }),
                );

                refreshDbRequest = request;

                await request.unwrap();

                if (cancelled) {
                    return;
                }

                setPage(1);
            } catch (err: unknown) {
                const errorName = err instanceof Error ? err.name : "";

                if (
                    cancelled ||
                    err === "REQUEST_ABORTED" ||
                    errorName === "AbortError"
                ) {
                    return;
                }

                console.error(
                    `Lỗi chuẩn bị news ${symbol}:`,
                    err instanceof Error ? err.message : err,
                );
            } finally {
                if (!cancelled) {
                    setIsPreparingNews(false);
                }
            }
        };

        void loadNews();

        return () => {
            // User đã chuyển mã.
            //
            // Ví dụ:
            // LDG đang request
            // → chuyển CII
            //
            // response LDG về sau sẽ không
            // tiếp tục import/fetch DB.
            cancelled = true;
            initialDbRequest.abort();
            activePythonRequest?.abort();
            syncController.abort();
            refreshDbRequest?.abort();
        };
    }, [symbol, isVNINDEX, dispatch]);

    // =====================================================
    // INFINITE SCROLL
    // =====================================================

    useEffect(() => {
        if (!symbol) {
            return;
        }

        const loadMore = () => {
            if (isFetchingMoreRef.current || isPreparingNews) {
                return;
            }

            // Mã thường:
            // nếu Redux hiện đang thuộc mã khác
            // thì tuyệt đối không load page tiếp.
            if (!isVNINDEX && currentSymbol !== symbol) {
                return;
            }

            const currentList = isVNINDEX ? vnindexList : list;

            const currentMeta = isVNINDEX ? vnindexMeta : meta;

            const total = Number(currentMeta?.total) || 0;

            const hasMore =
                typeof currentMeta?.hasMore === "boolean"
                    ? currentMeta.hasMore
                    : currentList.length < total;

            if (!hasMore) {
                return;
            }

            const nextPage = page + 1;

            isFetchingMoreRef.current = true;
            setIsFetchingMore(true);

            const request = isVNINDEX
                ? dispatch(
                      fetchAllNewsForVNINDEX({
                          page: nextPage,
                          limit,
                      }),
                  )
                : dispatch(
                      fetchNewsQuery({
                          symbol,
                          page: nextPage,
                          limit,
                      }),
                  );

            request
                .unwrap()
                .then(() => {
                    setPage(nextPage);
                })
                .catch((err: any) => {
                    console.error(
                        `Lỗi tải page ${nextPage} của ${symbol}:`,
                        err,
                    );
                })
                .finally(() => {
                    isFetchingMoreRef.current = false;
                    setIsFetchingMore(false);
                });
        };

        const trigger = loadMoreTriggerRef.current;

        if (!trigger) {
            return;
        }

        const observer = new IntersectionObserver(
            (entries) => {
                if (entries[0]?.isIntersecting) {
                    loadMore();
                }
            },
            {
                root: null,
                rootMargin: "250px 0px",
                threshold: 0,
            },
        );

        observer.observe(trigger);

        return () => {
            observer.disconnect();
        };
    }, [
        symbol,
        isVNINDEX,
        currentSymbol,
        page,

        list,
        meta,

        vnindexList,
        vnindexMeta,

        isFetchingMore,
        isPreparingNews,

        dispatch,
    ]);

    // =====================================================
    // PRICE
    // =====================================================

    const latestCandle = candleData[candleData.length - 1];

    const prevCandle = candleData[candleData.length - 2];

    const price = latestCandle?.close || 0;

    const prevPrice = prevCandle?.close || price;

    const change = price - prevPrice;

    const percent = prevPrice
        ? ((change / prevPrice) * 100).toFixed(2)
        : "0.00";

    const isUp = change > 0;

    const isDown = change < 0;

    // =====================================================
    // DISPLAY
    // =====================================================

    const displayList = isVNINDEX
        ? vnindexList
        : currentSymbol === symbol
          ? list
          : [];

    // Quan trọng:
    // đang đổi LDG -> CII
    //
    // KHÔNG render list LDG trong lúc CII load.
    if (isPreparingNews || (!isVNINDEX && currentSymbol !== symbol)) {
        return (
            <div className="p-4 text-slate-500 dark:text-slate-400 text-sm">
                Đang tải tin tức {symbol}...
            </div>
        );
    }

    if (error && !displayList?.length) {
        return <div className="p-4 text-rose-500 text-sm">Lỗi: {error}</div>;
    }

    if (!displayList?.length) {
        return (
            <div className="p-4 text-slate-500 dark:text-slate-400 text-sm">
                Chưa có tin tức
            </div>
        );
    }

    return (
        <div className="space-y-5">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">
                Bài viết
            </h2>

            <div className="space-y-3">
                {displayList.map((item) => (
                    <div
                        key={item.news_id || item.slug}
                        onClick={() => router.push(`/tin-tuc/${item?.slug}`)}
                        className="group min-h-[9rem] flex items-start gap-4 rounded-xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900/60 hover:bg-slate-50 dark:hover:bg-slate-800/90 p-4 transition-all duration-200 cursor-pointer shadow-sm hover:shadow-md"
                    >
                        {/* Image */}
                        <div className="relative w-[7.5rem] aspect-[4/3] flex-shrink-0 rounded-lg overflow-hidden bg-slate-100 dark:bg-slate-800 border border-slate-200/60 dark:border-slate-700/60">
                            {item.news_image_url ? (
                                <Image
                                    src={item.news_image_url}
                                    alt={item.news_title || "News"}
                                    fill
                                    className="object-cover transition-transform duration-300 group-hover:scale-105"
                                />
                            ) : (
                                <div className="flex items-center justify-center w-full h-full text-slate-400 dark:text-slate-500 text-xs">
                                    No Image
                                </div>
                            )}
                        </div>

                        {/* Content */}
                        <div className="flex-1 min-w-0">
                            <div className="flex items-center text-sm mb-1">
                                <span className="font-semibold text-blue-600 dark:text-blue-400 mr-2">
                                    {isVNINDEX
                                        ? StockIndex?.VNINDEX
                                        : item?.symbol || symbol}
                                </span>

                                <span
                                    className={`text-xs font-semibold ${
                                        isUp
                                            ? "text-emerald-600 dark:text-emerald-400"
                                            : isDown
                                              ? "text-rose-600 dark:text-rose-400"
                                              : "text-slate-400 dark:text-slate-400"
                                    }`}
                                >
                                    {isUp && "+"}
                                    {percent}%
                                </span>
                            </div>

                            <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100 line-clamp-2 group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors duration-200">
                                {item.news_title}
                            </h3>

                            <p className="text-sm text-slate-600 dark:text-slate-300 line-clamp-2 mt-1.5 leading-relaxed">
                                {item.news_short_content || (
                                    <span
                                        dangerouslySetInnerHTML={{
                                            __html: item.news_full_content
                                                ? item.news_full_content.slice(
                                                      0,
                                                      150,
                                                  ) + "..."
                                                : "",
                                        }}
                                    />
                                )}
                            </p>

                            <div className="flex items-center justify-between mt-2.5 text-xs text-slate-500 dark:text-slate-400">
                                <span>{formatDate(item.public_date)}</span>

                                <div className="flex items-center gap-3">
                                    <div className="flex items-center gap-1">
                                        <ThumbsUp className="w-3 h-3" />4
                                    </div>

                                    <div className="flex items-center gap-1">
                                        <MessageSquare className="w-3 h-3" />
                                        32
                                    </div>

                                    <div className="flex items-center gap-1">
                                        <Repeat2 className="w-3 h-3" />7
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                ))}

                <div
                    ref={loadMoreTriggerRef}
                    className="h-px w-full"
                    aria-hidden="true"
                />

                {isFetchingMore && (
                    <div className="flex justify-center py-4 text-sm text-slate-500 dark:text-slate-400">
                        Đang tải thêm tin tức...
                    </div>
                )}
            </div>
        </div>
    );
}
// "use client";

// import Image from "next/image";
// import { useEffect, useRef, useState } from "react";
// import { useDispatch } from "react-redux";
// import { useParams, useRouter } from "next/navigation";
// import { MessageSquare, Repeat2, ThumbsUp } from "lucide-react";

// import { AppDispatch, RootState } from "@/redux/store";

// import { useAppSelector } from "@/redux/hooks";

// import {
//     fetchNewsFromJson,
//     fetchNewsQuery,
//     fetchAllNewsForVNINDEX,
// } from "@/store/news/news.api";

// import { api } from "@/utils/axiosInstance";
// import { StockIndex } from "../enum";

// function formatDate(dateStr?: string) {
//     if (!dateStr) return "";

//     const date = new Date(dateStr);

//     if (isNaN(date.getTime())) {
//         return "";
//     }

//     const day = String(date.getDate()).padStart(2, "0");

//     const month = String(date.getMonth() + 1).padStart(2, "0");

//     const hours = String(date.getHours()).padStart(2, "0");

//     const minutes = String(date.getMinutes()).padStart(2, "0");

//     return `${day}/${month} ${hours}:${minutes}`;
// }

// export default function NewsListJson() {
//     const router = useRouter();

//     const dispatch = useDispatch<AppDispatch>();

//     const {
//         currentSymbol,

//         list,
//         meta,

//         vnindexList,
//         vnindexMeta,

//         error,
//     } = useAppSelector((state: RootState) => state.news);

//     const { candleData } = useAppSelector(
//         (state: RootState) => state.stockSymbols,
//     );

//     const params = useParams();

//     const symbol = String(params.stock || "")
//         .toUpperCase()
//         .trim();

//     const limit = 10;

//     const isVNINDEX = symbol === StockIndex?.VNINDEX;

//     const [page, setPage] = useState(1);

//     const [isFetchingMore, setIsFetchingMore] = useState(false);

//     const isFetchingMoreRef = useRef(false);
//     const loadMoreTriggerRef = useRef<HTMLDivElement | null>(null);

//     const [isPreparingNews, setIsPreparingNews] = useState(false);

//     // =====================================================
//     // LOAD NEWS
//     //
//     // Mã thường:
//     //
//     // Python
//     //   ↓
//     // import NestJS
//     //   ↓
//     // DB page 1
//     //
//     // Gộp thành 1 flow để tránh jsonData mã cũ
//     // trigger import cho mã mới.
//     // =====================================================

//     useEffect(() => {
//         if (!symbol) {
//             return;
//         }

//         let cancelled = false;

//         setPage(1);
//         isFetchingMoreRef.current = false;
//         setIsFetchingMore(false);

//         // =========================
//         // VNINDEX
//         // =========================

//         if (isVNINDEX) {
//             setIsPreparingNews(false);

//             dispatch(
//                 fetchAllNewsForVNINDEX({
//                     page: 1,
//                     limit,
//                 }),
//             );

//             return () => {
//                 cancelled = true;
//             };
//         }

//         // =========================
//         // STOCK
//         // =========================

//         setIsPreparingNews(true);

//         // Hiển thị dữ liệu đã có trong DB ngay. Không bắt giao diện phải chờ
//         // Python gọi vnstock_data xong rồi mới được tải page 1.
//         const initialDbRequest = dispatch(
//             fetchNewsQuery({
//                 symbol,
//                 page: 1,
//                 limit,
//             }),
//         );

//         const syncController = new AbortController();

//         let activePythonRequest: {
//             abort: () => void;
//             unwrap: () => Promise<unknown>;
//         } | null = null;

//         let refreshDbRequest: {
//             abort: () => void;
//             unwrap: () => Promise<unknown>;
//         } | null = null;

//         const sleep = (ms: number) =>
//             new Promise<void>((resolve) => {
//                 setTimeout(resolve, ms);
//             });

//         const shouldRetry = (err: any) => {
//             const status =
//                 err?.status ?? err?.response?.status ?? err?.originalStatus;

//             const code =
//                 err?.code ?? err?.data?.code ?? err?.response?.data?.code;

//             const message = String(
//                 err?.message ?? err?.data?.message ?? err?.data?.error ?? "",
//             );

//             return (
//                 status === 503 ||
//                 status === 504 ||
//                 code === "NEWS_UPSTREAM_TIMEOUT" ||
//                 code === "NEWS_UPSTREAM_UNAVAILABLE" ||
//                 message.includes("quá thời gian") ||
//                 message.includes("UPSTREAM_TIMEOUT")
//             );
//         };

//         const preparePythonNews = async () => {
//             const maxAttempts = 20;
//             const retryDelay = 3000;

//             for (let attempt = 1; attempt <= maxAttempts; attempt++) {
//                 if (cancelled) {
//                     return false;
//                 }

//                 try {
//                     const request = dispatch(fetchNewsFromJson(symbol));

//                     activePythonRequest = request;

//                     await request.unwrap();

//                     console.log(`✅ Python news ${symbol} đã sẵn sàng`);

//                     return true;
//                 } catch (err: unknown) {
//                     if (cancelled) {
//                         return false;
//                     }

//                     if (!shouldRetry(err)) {
//                         throw err;
//                     }

//                     console.log(
//                         `⏳ News ${symbol} chưa sẵn sàng ` +
//                             `(lần ${attempt}/${maxAttempts})`,
//                     );

//                     if (attempt === maxAttempts) {
//                         throw err;
//                     }

//                     await sleep(retryDelay);
//                 }
//             }

//             return false;
//         };

//         const loadNews = async () => {
//             try {
//                 // Python có thể timeout ở request đầu,
//                 // nhưng worker backend vẫn tiếp tục chạy.
//                 //
//                 // Frontend retry đến khi cache sẵn sàng.
//                 const ready = await preparePythonNews();

//                 if (!ready || cancelled) {
//                     return;
//                 }

//                 // Cache Python đã có
//                 // → import JSON vào NestJS DB
//                 await api.post(
//                     `/news/import/${symbol}`,
//                     {
//                         page: 1,
//                         limit,
//                     },
//                     {
//                         signal: syncController.signal,
//                     },
//                 );

//                 if (cancelled) {
//                     return;
//                 }

//                 // Import xong
//                 // → lấy page 1 mới từ DB
//                 const request = dispatch(
//                     fetchNewsQuery({
//                         symbol,
//                         page: 1,
//                         limit,
//                     }),
//                 );

//                 refreshDbRequest = request;

//                 await request.unwrap();

//                 if (cancelled) {
//                     return;
//                 }

//                 setPage(1);
//             } catch (err: unknown) {
//                 const errorName = err instanceof Error ? err.name : "";

//                 if (
//                     cancelled ||
//                     err === "REQUEST_ABORTED" ||
//                     errorName === "AbortError"
//                 ) {
//                     return;
//                 }

//                 console.error(
//                     `Lỗi chuẩn bị news ${symbol}:`,
//                     err instanceof Error ? err.message : err,
//                 );
//             } finally {
//                 if (!cancelled) {
//                     setIsPreparingNews(false);
//                 }
//             }
//         };

//         void loadNews();

//         return () => {
//             // User đã chuyển mã.
//             //
//             // Ví dụ:
//             // LDG đang request
//             // → chuyển CII
//             //
//             // response LDG về sau sẽ không
//             // tiếp tục import/fetch DB.
//             cancelled = true;
//             initialDbRequest.abort();
//             activePythonRequest?.abort();
//             syncController.abort();
//             refreshDbRequest?.abort();
//         };
//     }, [symbol, isVNINDEX, dispatch]);

//     // =====================================================
//     // INFINITE SCROLL
//     // =====================================================

//     useEffect(() => {
//         if (!symbol) {
//             return;
//         }

//         const loadMore = () => {
//             if (isFetchingMoreRef.current || isPreparingNews) {
//                 return;
//             }

//             // Mã thường:
//             // nếu Redux hiện đang thuộc mã khác
//             // thì tuyệt đối không load page tiếp.
//             if (!isVNINDEX && currentSymbol !== symbol) {
//                 return;
//             }

//             const currentList = isVNINDEX ? vnindexList : list;

//             const currentMeta = isVNINDEX ? vnindexMeta : meta;

//             const total = Number(currentMeta?.total) || 0;

//             const hasMore =
//                 typeof currentMeta?.hasMore === "boolean"
//                     ? currentMeta.hasMore
//                     : currentList.length < total;

//             if (!hasMore) {
//                 return;
//             }

//             const nextPage = page + 1;

//             isFetchingMoreRef.current = true;
//             setIsFetchingMore(true);

//             const request = isVNINDEX
//                 ? dispatch(
//                       fetchAllNewsForVNINDEX({
//                           page: nextPage,
//                           limit,
//                       }),
//                   )
//                 : dispatch(
//                       fetchNewsQuery({
//                           symbol,
//                           page: nextPage,
//                           limit,
//                       }),
//                   );

//             request
//                 .unwrap()
//                 .then(() => {
//                     setPage(nextPage);
//                 })
//                 .catch((err: any) => {
//                     console.error(
//                         `Lỗi tải page ${nextPage} của ${symbol}:`,
//                         err,
//                     );
//                 })
//                 .finally(() => {
//                     isFetchingMoreRef.current = false;
//                     setIsFetchingMore(false);
//                 });
//         };

//         const trigger = loadMoreTriggerRef.current;

//         if (!trigger) {
//             return;
//         }

//         const observer = new IntersectionObserver(
//             (entries) => {
//                 if (entries[0]?.isIntersecting) {
//                     loadMore();
//                 }
//             },
//             {
//                 root: null,
//                 rootMargin: "250px 0px",
//                 threshold: 0,
//             },
//         );

//         observer.observe(trigger);

//         return () => {
//             observer.disconnect();
//         };
//     }, [
//         symbol,
//         isVNINDEX,
//         currentSymbol,
//         page,

//         list,
//         meta,

//         vnindexList,
//         vnindexMeta,

//         isFetchingMore,
//         isPreparingNews,

//         dispatch,
//     ]);

//     // =====================================================
//     // PRICE
//     // =====================================================

//     const latestCandle = candleData[candleData.length - 1];

//     const prevCandle = candleData[candleData.length - 2];

//     const price = latestCandle?.close || 0;

//     const prevPrice = prevCandle?.close || price;

//     const change = price - prevPrice;

//     const percent = prevPrice
//         ? ((change / prevPrice) * 100).toFixed(2)
//         : "0.00";

//     const isUp = change > 0;

//     const isDown = change < 0;

//     // =====================================================
//     // DISPLAY
//     // =====================================================

//     const displayList = isVNINDEX
//         ? vnindexList
//         : currentSymbol === symbol
//           ? list
//           : [];

//     // Quan trọng:
//     // đang đổi LDG -> CII
//     //
//     // KHÔNG render list LDG trong lúc CII load.
//     if (isPreparingNews || (!isVNINDEX && currentSymbol !== symbol)) {
//         return (
//             <div className="p-4 text-slate-500 dark:text-slate-400 text-sm">
//                 Đang tải tin tức {symbol}...
//             </div>
//         );
//     }

//     if (error && !displayList?.length) {
//         return <div className="p-4 text-rose-500 text-sm">Lỗi: {error}</div>;
//     }

//     if (!displayList?.length) {
//         return (
//             <div className="p-4 text-slate-500 dark:text-slate-400 text-sm">
//                 Chưa có tin tức
//             </div>
//         );
//     }

//     return (
//         <div className="space-y-5">
//             <h2 className="text-lg font-semibold text-slate-900 dark:text-white">
//                 Bài viết
//             </h2>

//             <div className="space-y-3">
//                 {displayList.map((item) => (
//                     <div
//                         key={item.news_id || item.slug}
//                         onClick={() => router.push(`/tin-tuc/${item?.slug}`)}
//                         className="group min-h-[9rem] flex items-start gap-4 rounded-xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900/60 hover:bg-slate-50 dark:hover:bg-slate-800/90 p-4 transition-all duration-200 cursor-pointer shadow-sm hover:shadow-md"
//                     >
//                         {/* Image */}
//                         <div className="relative w-[7.5rem] aspect-[4/3] flex-shrink-0 rounded-lg overflow-hidden bg-slate-100 dark:bg-slate-800 border border-slate-200/60 dark:border-slate-700/60">
//                             {item.news_image_url ? (
//                                 <Image
//                                     src={item.news_image_url}
//                                     alt={item.news_title || "News"}
//                                     fill
//                                     className="object-cover transition-transform duration-300 group-hover:scale-105"
//                                 />
//                             ) : (
//                                 <div className="flex items-center justify-center w-full h-full text-slate-400 dark:text-slate-500 text-xs">
//                                     No Image
//                                 </div>
//                             )}
//                         </div>

//                         {/* Content */}
//                         <div className="flex-1 min-w-0">
//                             <div className="flex items-center text-sm mb-1">
//                                 <span className="font-semibold text-blue-600 dark:text-blue-400 mr-2">
//                                     {isVNINDEX
//                                         ? StockIndex?.VNINDEX
//                                         : item?.symbol || symbol}
//                                 </span>

//                                 <span
//                                     className={`text-xs font-semibold ${
//                                         isUp
//                                             ? "text-emerald-600 dark:text-emerald-400"
//                                             : isDown
//                                               ? "text-rose-600 dark:text-rose-400"
//                                               : "text-slate-400 dark:text-slate-400"
//                                     }`}
//                                 >
//                                     {isUp && "+"}
//                                     {percent}%
//                                 </span>
//                             </div>

//                             <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100 line-clamp-2 group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors duration-200">
//                                 {item.news_title}
//                             </h3>

//                             <p className="text-sm text-slate-600 dark:text-slate-300 line-clamp-2 mt-1.5 leading-relaxed">
//                                 {item.news_short_content || (
//                                     <span
//                                         dangerouslySetInnerHTML={{
//                                             __html: item.news_full_content
//                                                 ? item.news_full_content.slice(
//                                                       0,
//                                                       150,
//                                                   ) + "..."
//                                                 : "",
//                                         }}
//                                     />
//                                 )}
//                             </p>

//                             <div className="flex items-center justify-between mt-2.5 text-xs text-slate-500 dark:text-slate-400">
//                                 <span>{formatDate(item.public_date)}</span>

//                                 <div className="flex items-center gap-3">
//                                     <div className="flex items-center gap-1">
//                                         <ThumbsUp className="w-3 h-3" />4
//                                     </div>

//                                     <div className="flex items-center gap-1">
//                                         <MessageSquare className="w-3 h-3" />
//                                         32
//                                     </div>

//                                     <div className="flex items-center gap-1">
//                                         <Repeat2 className="w-3 h-3" />7
//                                     </div>
//                                 </div>
//                             </div>
//                         </div>
//                     </div>
//                 ))}

//                 <div
//                     ref={loadMoreTriggerRef}
//                     className="h-px w-full"
//                     aria-hidden="true"
//                 />

//                 {isFetchingMore && (
//                     <div className="flex justify-center py-4 text-sm text-slate-500 dark:text-slate-400">
//                         Đang tải thêm tin tức...
//                     </div>
//                 )}
//             </div>
//         </div>
//     );
// }