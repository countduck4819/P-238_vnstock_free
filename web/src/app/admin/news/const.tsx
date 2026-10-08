"use client";

import Image from "next/image";

export const newsColumns = [
    {
        key: "news_image_url",
        header: "Ảnh",
        render: (item: any) => (
            <div className="min-w-[2rem] min-h-[2rem] flex justify-center items-center">
                {item.news_image_url ? (
                    <Image
                        src={item.news_image_url}
                        alt={item.news_title}
                        width={64}
                        height={64}
                        className="inline-block min-w-[2rem] min-h-[2rem] rounded-md object-cover border border-gray-700"
                    />
                ) : (
                    "—"
                )}
            </div>
        ),
    },
    {
        key: "news_title",
        header: "Tiêu đề",
        render: (item: any) => item.news_title || "—",
    },
    {
        key: "symbol",
        header: "Mã CK",
        render: (item: any) => item.symbol || "—",
    },
    {
        key: "news_short_content",
        header: "Tóm tắt",
        render: (item: any) =>
            item.news_short_content
                ? item.news_short_content.length > 150
                    ? item.news_short_content.slice(0, 150) + "…"
                    : item.news_short_content
                : "—",
    },
    {
        key: "public_date",
        header: "Ngày đăng",
        render: (item: any) =>
            item.public_date
                ? new Date(item.public_date).toLocaleDateString("vi-VN")
                : "—",
    },
    {
        key: "news_source_link",
        header: "Nguồn tin",
        render: (item: any) =>
            item.news_source_link ? (
                <a
                    href={item.news_source_link}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-indigo-400 hover:underline"
                >
                    Link gốc
                </a>
            ) : (
                "VNStock"
            ),
    },
];
