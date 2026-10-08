"use client";

import { useEffect, useState } from "react";
import {
    ExternalLink,
    Loader2,
} from "lucide-react";

export default function PDFViewer({
    url,
}: {
    url: string;
}) {
    const [loading, setLoading] =
        useState(true);

    const normalizedUrl = url
        .replace(/&amp;/g, "&")
        .replace(
            /^http:\/\/static2\.vietstock\.vn/i,
            "https://static2.vietstock.vn",
        );

    const viewerUrl =
        `https://docs.google.com/gview?embedded=true&url=${encodeURIComponent(
            normalizedUrl,
        )}`;

    useEffect(() => {
        setLoading(true);

        const timeout = setTimeout(() => {
            setLoading(false);
        }, 12000);

        return () => {
            clearTimeout(timeout);
        };
    }, [normalizedUrl]);

    return (
        <div className="w-full my-8">
            <div className="relative w-full h-[60rem] rounded-lg overflow-hidden border border-gray-200 bg-white">
                {loading && (
                    <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-white">
                        <Loader2 className="w-6 h-6 text-[#111164] animate-spin mb-2" />

                        <span className="text-sm text-[#111164]">
                            Đang tải tài liệu...
                        </span>
                    </div>
                )}

                <iframe
                    src={viewerUrl}
                    title="Tài liệu PDF"
                    className="w-full h-full border-none bg-white"
                    onLoad={() =>
                        setLoading(false)
                    }
                />
            </div>

            <a
                href={normalizedUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 mt-4 px-4 py-2 text-sm font-medium text-[#111164] border border-[#111164]/20 rounded-lg hover:bg-[#111164]/5 transition-colors"
            >
                <ExternalLink className="w-4 h-4" />

                Mở tài liệu PDF
            </a>
        </div>
    );
}