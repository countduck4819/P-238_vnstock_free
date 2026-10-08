import type { NextConfig } from "next";

const nextConfig: NextConfig = {
    /* config options here */
    reactStrictMode: false,
    images: {
        remotePatterns: [
            {
                protocol: "https",
                hostname: "**",
            },
            {
                protocol: "http",
                hostname: "**",
            },
        ],
    },
    async rewrites() {
        const internalApiBase = (
            process.env.INTERNAL_API_BASE_URL || "http://localhost:8000/api"
        ).replace(/\/$/, "");
        const pythonApiBase = (
            process.env.INTERNAL_PYTHON_API_URL ||
            process.env.PYTHON_API_URL ||
            "http://python_data:6060/api"
        ).replace(/\/$/, "");
        return [
            {
                source: "/api/python/:path*",
                destination: `${pythonApiBase}/:path*`,
            },
            {
                source: "/api/:path*",
                destination: `${internalApiBase}/:path*`,
            },
        ];
    },
};

export default nextConfig;
