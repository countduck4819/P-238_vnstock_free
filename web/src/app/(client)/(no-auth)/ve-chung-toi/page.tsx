"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function FinSightPage() {
    const router = useRouter();

    useEffect(() => {
        router.replace("/");
    }, [router]);

    return (
        <div className="min-h-[70vh] flex items-center justify-center bg-white dark:bg-slate-950">
            <div className="flex flex-col items-center gap-3">
                <div className="w-8 h-8 rounded-full border-2 border-indigo-600 border-t-transparent animate-spin" />
                <p className="text-xs text-slate-500">Đang chuyển đến Giới thiệu FinSight...</p>
            </div>
        </div>
    );
}
