import axios from "axios";
import { toast } from "react-toastify";

export const API_BASE = "/api";

function getCookie(name: string): string | null {
    if (typeof document === "undefined") return null;
    const match = document.cookie
        ?.split("; ")
        ?.find((row) => row.startsWith(name + "="));
    return match ? decodeURIComponent(match.split("=")[1]) : null;
}

function setCookie(name: string, value: string, maxAgeSeconds = 60 * 15) {
    document.cookie = `${encodeURIComponent(name)}=${encodeURIComponent(
        value
    )}; Path=/; Max-Age=${maxAgeSeconds}; SameSite=Lax; Secure`;
}

function removeCookie(name: string) {
    document.cookie = `${encodeURIComponent(name)}=; Path=/; Max-Age=0`;
}

export const api = axios.create({
    baseURL: API_BASE,
    headers: { "Content-Type": "application/json" },
    withCredentials: true,
});

api.interceptors.request.use(
    (config) => {
        const token = getCookie("accessToken");
        if (token) config.headers.Authorization = `Bearer ${token}`;
        return config;
    },
    (error) => Promise.reject(error)
);

api.interceptors.response.use(
    (response) => {
        const data = response?.data;
        if (data === 0 || data === null || data === undefined) {
            toast.error("API trả về dữ liệu rỗng hoặc không hợp lệ!");
            return Promise.reject("API trả về dữ liệu rỗng hoặc không hợp lệ!");
        }
        return response;
    },
    async (error) => {
        const originalRequest = error.config || {};
        const res = error.response;
        const status = res?.status ?? 0;

        let msg =
            res?.data?.message ||
            res?.data?.error ||
            error.message ||
            "Đã xảy ra lỗi!";
        if (Array.isArray(msg)) msg = msg[0];
        if (typeof msg === "object") msg = JSON.stringify(msg);

        if (status === 0) {
            toast.error("Không kết nối được máy chủ!");
            return Promise.reject(msg);
        }

        if (status === 400) {
            toast.error(msg);
            return Promise.reject(msg);
        }

        if (
            status === 401 &&
            !originalRequest._retry &&
            getCookie("refreshToken")
        ) {
            originalRequest._retry = true;
            try {
                const refreshToken = getCookie("refreshToken");
                const r = await api.post("/auth/refresh-token", {
                    refreshToken,
                });
                const newAccessToken =
                    r.data?.data?.tokens?.accessToken ||
                    r.data?.tokens?.accessToken;
                if (newAccessToken) {
                    setCookie("accessToken", newAccessToken);
                    originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
                    return api(originalRequest);
                }
                throw new Error("Không nhận được accessToken mới");
            } catch (err) {
                toast.error(
                    "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại!"
                );
                removeCookie("accessToken");
                removeCookie("refreshToken");
                if (typeof window !== "undefined") {
                    setTimeout(() => (window.location.href = "/login"), 1000);
                }
                return Promise.reject(err);
            }
        }

        toast.error(msg);
        return Promise.reject(msg);
    }
);
