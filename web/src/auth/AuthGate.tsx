"use client";

import { useEffect } from "react";
import { useAuth } from "./AuthProvider";
import { usePathname, useRouter } from "next/navigation";
import Loading from "@/share/components/Loading";
import { publicRouters } from "@/share/const/const";

const publicRoutes = ["/", ...publicRouters, "/nang-cap-hoi-vien"];

export default function AuthGate({ children }: { children: React.ReactNode }) {
    const { user, loading, isAuthenticated } = useAuth();
    const router = useRouter();
    const pathname = usePathname();
    useEffect(() => {
        if (loading) return;
        const isPublic = publicRoutes.some((route) => {
            if (route === "/") return pathname === "/";
            return pathname.startsWith(route);
        });
        if (!isAuthenticated && !isPublic) router.replace("/login");
        if (isAuthenticated && pathname === "/login") router.replace("/home");
    }, [loading, isAuthenticated, pathname]);

    if (loading) {
        return <Loading></Loading>;
    }

    return <>{children}</>;
}
