"use client";

import Image from "next/image";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, TrendingDown, TrendingUp } from "lucide-react";
import { toast } from "react-toastify";

import { useAppDispatch, useAppSelector } from "@/redux/hooks";
import { fetchNewsDetailBySlug } from "@/store/news/news.api";

import Loading from "@/share/components/Loading";
import PDFViewer from "@/share/components/PDFViewer";
import { renderWithEmbed } from "@/lib/utils";
import { api } from "@/utils/axiosInstance";
import { pythonApiUrl } from "@/utils/pythonApi";

export default function NewsDetailPage() {
    const { slug } = useParams();
    const router = useRouter();

    const dispatch = useAppDispatch();

    const { detail, loading, error } = useAppSelector((state) => state.news);

    const [resolvedPdfSlug, setResolvedPdfSlug] = useState<string | null>(
        null,
    );

    useEffect(() => {
        if (slug) {
            dispatch(fetchNewsDetailBySlug(String(slug)));
        }
    }, [slug, dispatch]);

    useEffect(() => {
        if (error) {
            toast.error(error);
        }
    }, [error]);

    const content = String(detail?.news_full_content || "");

    const pdfUrls: string[] = Array.from(
        new Set<string>(
            (
                content.match(
                    /https?:\/\/[^\s"'<>]+\.pdf(?:\?[^\s"'<>]*)?/gi,
                ) ?? []
            ).map((url: string) =>
                url.replace(/&amp;/g, "&").replace(/[.,;)\]}]+$/, ""),
            ),
        ),
    );

    const isPdfPending =
        /\.pdf\b/i.test(content) && pdfUrls.length === 0;

    useEffect(() => {
        const symbol = String(detail?.symbol || "")
            .toUpperCase()
            .trim();
        const detailSlug = String(detail?.slug || "");

        if (
            !slug ||
            detailSlug !== String(slug) ||
            !symbol ||
            !isPdfPending
        ) {
            return;
        }

        let cancelled = false;
        const controller = new AbortController();

        const wait = (milliseconds: number) =>
            new Promise<void>((resolve) => {
                window.setTimeout(resolve, milliseconds);
            });

        const enrichPdf = async () => {
            try {
                for (let attempt = 0; attempt < 45; attempt += 1) {
                    const response = await fetch(
                        pythonApiUrl(`/news/${symbol}`),
                        { signal: controller.signal },
                    );

                    if (!response.ok) {
                        throw new Error(`HTTP ${response.status}`);
                    }

                    const metadata = (await response.json()) as {
                        pdf_status?: string;
                    };

                    if (cancelled) {
                        return;
                    }

                    if (
                        metadata.pdf_status === "ready" ||
                        metadata.pdf_status === "unavailable"
                    ) {
                        await api.post(
                            `/news/import/${symbol}`,
                            {},
                            { signal: controller.signal },
                        );

                        if (cancelled) {
                            return;
                        }

                        await dispatch(
                            fetchNewsDetailBySlug(String(slug)),
                        ).unwrap();

                        if (!cancelled) {
                            setResolvedPdfSlug(String(slug));
                        }

                        return;
                    }

                    if (metadata.pdf_status === "error") {
                        setResolvedPdfSlug(String(slug));
                        return;
                    }

                    await wait(2000);
                }

                if (!cancelled) {
                    setResolvedPdfSlug(String(slug));
                }
            } catch (enrichError) {
                if (
                    !cancelled &&
                    !(enrichError instanceof DOMException &&
                        enrichError.name === "AbortError")
                ) {
                    console.error("Lỗi tải tài liệu PDF:", enrichError);
                    setResolvedPdfSlug(String(slug));
                }
            }
        };

        void enrichPdf();

        return () => {
            cancelled = true;
            controller.abort();
        };
    }, [detail?.slug, detail?.symbol, dispatch, isPdfPending, slug]);

    const isWaitingForPdf =
        isPdfPending && resolvedPdfSlug !== String(slug);

    if (loading || isWaitingForPdf) {
        return <Loading />;
    }

    if (!detail) {
        return (
            <div className="p-10 text-center text-gray-500">
                Không tìm thấy bài viết
            </div>
        );
    }

    const hasChange = typeof detail.change_percent === "number";
    const changePercent = detail.change_percent || 0;

    const isUp = changePercent > 0;

    const isDown = changePercent < 0;

    return (
        <article className="max-w-4xl mx-auto px-4 py-10">
            {/* Back */}
            <button
                type="button"
                onClick={() => router.back()}
                className="flex items-center text-sm text-slate-500 dark:text-slate-400 hover:text-blue-600 dark:hover:text-blue-400 transition mb-6"
            >
                <ArrowLeft className="w-4 h-4 mr-1" />
                Quay lại
            </button>

            {/* Tiêu đề */}
            <h1 className="text-3xl md:text-4xl font-bold text-slate-900 dark:text-slate-100 mb-2 leading-snug">
                {detail.news_title}
            </h1>

            {/* Thông tin phụ */}
            <div className="flex items-center text-sm text-slate-500 dark:text-slate-400 flex-wrap gap-2 mb-4">
                <span>
                    {detail.source
                        ? `Nguồn: ${detail.source}`
                        : "Tin doanh nghiệp"}
                </span>

                {detail.public_date && (
                    <>
                        <span>•</span>

                        <span>
                            {new Date(detail.public_date).toLocaleDateString(
                                "vi-VN",
                            )}{" "}
                            {new Date(detail.public_date).toLocaleTimeString(
                                "vi-VN",
                                {
                                    hour: "2-digit",
                                    minute: "2-digit",
                                },
                            )}
                        </span>
                    </>
                )}
            </div>

            {/* Mã cổ phiếu (ẩn % khi chưa có dữ liệu giá thay vì hiện 0%) */}
            {detail.symbol && (
                <div className="inline-flex items-center px-3 py-1 rounded-full text-sm font-semibold bg-slate-100 dark:bg-slate-800 border border-slate-200/60 dark:border-slate-700/60 mb-6">
                    <span className="mr-2 text-blue-600 dark:text-blue-400">{detail.symbol}</span>

                    {isUp && (
                        <span className="text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
                            <TrendingUp className="w-3 h-3" />+{changePercent}%
                        </span>
                    )}

                    {isDown && (
                        <span className="text-rose-600 dark:text-rose-400 flex items-center gap-1">
                            <TrendingDown className="w-3 h-3" />
                            {changePercent}%
                        </span>
                    )}

                    {hasChange && !isUp && !isDown && <span className="text-slate-500 dark:text-slate-400">0%</span>}
                </div>
            )}

            {/* Ảnh đại diện */}
            {detail.news_image_url && (
                <div className="w-full rounded-xl overflow-hidden mb-8 shadow-sm">
                    <Image
                        src={detail.news_image_url}
                        alt={detail.news_title}
                        width={800}
                        height={500}
                        className="w-full h-auto object-cover"
                    />
                </div>
            )}

            {/* Nội dung */}
            <div
                className="prose prose-lg dark:prose-invert max-w-none text-slate-800 dark:text-slate-200 leading-relaxed [overflow-wrap:anywhere]"
                dangerouslySetInnerHTML={{
                    __html: renderWithEmbed(detail.news_full_content || ""),
                }}
            />

            {/* PDF */}
            {pdfUrls.map((url) => (
                <PDFViewer key={url} url={url} />
            ))}
        </article>
    );
}
