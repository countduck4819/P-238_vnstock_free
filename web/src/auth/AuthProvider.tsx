"use client";

import { createContext, useContext, useEffect, useState } from "react";
import jwt from "jsonwebtoken";
import { Role } from "@/share/enum";
import { AccountType, Gender } from "@/store/users/user.reducer";
import { api } from "@/utils/axiosInstance";
import { usePathname } from "next/navigation";

export interface User {
    id: number;
    username: string;
    fullName?: string;
    email: string;
    address?: string;
    citizenId?: string;
    role: Role;
    gender?: Gender;
    accountType?: AccountType;
    avatar?: string;
    exp?: number;
}

interface AuthContextType {
    user: User | null;
    loading: boolean;
    isAuthenticated: boolean;
    logout: () => Promise<void>;
    refetchUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
    const [user, setUser] = useState<User | null>(null);
    const [loading, setLoading] = useState(true);
    const pathname = usePathname();
    const getAccessToken = () => {
        const match = document.cookie.match(/accessToken=([^;]+)/);
        return match ? match[1] : null;
    };

    useEffect(() => {
        if (!user && !loading) refetchUser();
    }, [pathname]);

    useEffect(() => {
        const token = getAccessToken();
        if (token) {
            try {
                const decoded = jwt.decode(token) as User | null;
                if (decoded) setUser(decoded);
            } catch {}
        }
        refetchUser();
    }, []);

    const refetchUser = async () => {
        const token = getAccessToken();
        if (!token) {
            setUser(null);
            setLoading(false);
            return;
        }

        try {
            setLoading(true);
            const res = await fetch(
                `${process.env.NEXT_PUBLIC_API_BASE_URL}/auth/me`,
                {
                    headers: { Authorization: `Bearer ${token}` },
                    credentials: "include",
                }
            );
            if (!res.ok) throw new Error("Unauthorized");
            const { data } = await res.json();
            setUser(data?.[0]);
        } catch {
            setUser(null);
        } finally {
            setLoading(false);
        }
    };

    const logout = async () => {
        await api.post("/auth/logout");
        document.cookie = "accessToken=; Max-Age=0; Path=/";
        document.cookie = "refreshToken=; Max-Age=0; Path=/";
        setUser(null);
        window.location.href = "/";
    };

    return (
        <AuthContext.Provider
            value={{
                user,
                loading,
                isAuthenticated: !!user,
                logout,
                refetchUser,
            }}
        >
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    const ctx = useContext(AuthContext);
    if (!ctx) throw new Error("useAuth must be used within AuthProvider");
    return ctx;
}
