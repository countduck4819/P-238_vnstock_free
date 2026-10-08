import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "@/css/globals.css";
import { Providers } from "./providers";
import { AuthProvider } from "@/auth/AuthProvider";
import AuthGate from "@/auth/AuthGate";
import { ToastContainer } from "react-toastify";
import "react-toastify/dist/ReactToastify.css";
import Script from "next/script";
import Loading from "@/share/components/Loading";

const geistSans = Geist({
    variable: "--font-geist-sans",
    subsets: ["latin"],
});

const geistMono = Geist_Mono({
    variable: "--font-geist-mono",
    subsets: ["latin"],
});

const siteUrl = process?.env.DOMAIN_WEB || "http://localhost:3000";

const websiteJsonLd = {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: "FinSight",
    alternateName: "FinSight Chứng Khoán",
    url: siteUrl,
};

export const metadata: Metadata = {
    metadataBase: new URL(siteUrl),

    title: {
        default: "FinSight - AI phân tích chứng khoán Việt Nam",
        template: "%s | FinSight",
    },

    description:
        "FinSight là nền tảng AI hỗ trợ phân tích chứng khoán Việt Nam, kết hợp dữ liệu thị trường, phân tích kỹ thuật, báo cáo tài chính, tin tức, Machine Learning, Deep Learning và trợ lý AI tiếng Việt.",

    applicationName: "FinSight",
    category: "Finance",

    keywords: [
        "FinSight",
        "chứng khoán Việt Nam",
        "phân tích cổ phiếu",
        "AI chứng khoán",
        "VN-Index",
        "Machine Learning",
        "phân tích kỹ thuật chứng khoán",
        "phân tích báo cáo tài chính",
        "trợ lý AI tài chính",
    ],

    authors: [{ name: "FinSight Team" }],
    creator: "FinSight Team",
    publisher: "FinSight",

    alternates: {
        canonical: "/",
    },

    openGraph: {
        type: "website",
        locale: "vi_VN",
        url: "/",
        siteName: "FinSight",

        title: "FinSight - AI phân tích chứng khoán Việt Nam",

        description:
            "Phân tích thị trường, cổ phiếu và báo cáo tài chính bằng AI với dữ liệu thực tế, Machine Learning và trợ lý AI tiếng Việt.",

        images: [
            {
                url: "/images/thumbnail.png",
                width: 1000,
                height: 625,
                alt: "FinSight - Nền tảng AI phân tích chứng khoán Việt Nam",
            },
        ],
    },

    twitter: {
        card: "summary_large_image",

        title: "FinSight - AI phân tích chứng khoán Việt Nam",

        description:
            "Phân tích thị trường, cổ phiếu và báo cáo tài chính bằng AI với dữ liệu thực tế và trợ lý AI tiếng Việt.",

        images: ["/images/thumbnail.png"],
    },

    robots: {
        index: true,
        follow: true,

        googleBot: {
            index: true,
            follow: true,
            "max-image-preview": "large",
        },
    },

    icons: {
        icon: [
            { url: "/favicon.ico" },
            { url: "/favicon-32x32.png", sizes: "32x32", type: "image/png" },
            { url: "/favicon-16x16.png", sizes: "16x16", type: "image/png" },
        ],

        apple: [
            {
                url: "/apple-touch-icon.png",
                sizes: "180x180",
                type: "image/png",
            },
        ],
    },
};

import { ThemeProvider } from "@/components/theme/ThemeProvider";

export default function RootLayout({
    children,
}: Readonly<{
    children: React.ReactNode;
}>) {
    return (
        <html lang="vi" suppressHydrationWarning>
            <body
                className={`${geistSans.variable} ${geistMono.variable} antialiased bg-background text-foreground transition-colors duration-200`}
            >
                <script
                    type="application/ld+json"
                    dangerouslySetInnerHTML={{
                        __html: JSON.stringify(websiteJsonLd),
                    }}
                />
                <ThemeProvider defaultTheme="system">
                    <AuthProvider>
                        <AuthGate>
                            <Providers>
                                {children}
                                <ToastContainer
                                    position="top-right"
                                    autoClose={3000}
                                    pauseOnHover
                                    newestOnTop
                                    closeOnClick
                                    theme="colored"
                                />
                            </Providers>
                        </AuthGate>
                    </AuthProvider>
                </ThemeProvider>
                {/* ⚡ SDK hiển thị TradingView */}
                <Script
                    src="https://s3.tradingview.com/tv.js"
                    strategy="beforeInteractive"
                />
            </body>
        </html>
    );
}
