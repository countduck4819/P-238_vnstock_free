"use client";

import { ReactNode, useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";

import { Form } from "@/components/ui/form";

import { cn } from "@/lib/utils";
import { FormInput } from "@/share/components/FormInput";
import { FormButton } from "@/share/components/FormButtom";
import { FaGoogle } from "react-icons/fa";
import { FaFacebook } from "react-icons/fa";
import { api, API_BASE } from "@/utils/axiosInstance";
import Link from "next/link";

const loginSchema = z.object({
    email: z.string().email("Email không hợp lệ"),
    password: z.string().min(6, "Mật khẩu tối thiểu 6 ký tự"),
});

type LoginValues = z.infer<typeof loginSchema>;

export default function Login() {
    const router = useRouter();
    const [err, setErr] = useState("");
    const form = useForm<LoginValues>({
        resolver: zodResolver(loginSchema),
        defaultValues: { email: "", password: "" },
    });

    const onSubmit = async (values: LoginValues) => {
        setErr("");
        try {
            const res = await fetch(
                `${API_BASE}/auth/login`,
                {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    credentials: "include",
                    body: JSON.stringify(values),
                }
            );
            const data = await res.json();
            if (!data?.code) throw new Error(data?.message || "Đăng nhập thất bại");

            // const accessMaxAge = 60 * 15;

            // 7 ngày = 60 * 60 * 24 * 7 = 604800 giây
            const refreshMaxAge = 60 * 60 * 24 * 7;

            // Nếu backend chưa set cookie, tự set phía FE:
            if (data?.data?.tokens?.accessToken)
                document.cookie = `accessToken=${data.data.tokens.accessToken}; Path=/; SameSite=Lax;`;
            if (data?.data?.tokens?.refreshToken)
                document.cookie = `refreshToken=${data.data.tokens.refreshToken}; Path=/; SameSite=Lax; Max-Age=${refreshMaxAge}`;
            setTimeout(() => router.push("/home"), 50);
        } catch (e: any) {
            setErr(e.message);
        }
    };

    const loading = form.formState.isSubmitting;

    return (
        <main className="min-h-screen flex items-center justify-center bg-gradient-to-br from-[#F9F5FF] to-[#F3E8FF] p-6">
            <div className="w-full max-w-md relative overflow-hidden rounded-2xl bg-white/70 backdrop-blur-xl border border-[#E0CCFF] shadow-[0_10px_30px_rgba(147,51,234,0.1)] animate-fadeIn">
                <div className="absolute inset-0 pointer-events-none">
                    <div className="absolute -top-32 left-20 w-72 h-72 bg-[#C084FC]/40 blur-3xl rounded-full animate-pulse"></div>
                    <div className="absolute -bottom-32 right-20 w-72 h-72 bg-[#7C3AED]/30 blur-3xl rounded-full animate-pulse delay-300"></div>
                </div>
                <div className="relative z-10 p-8">
                    <h1 className="text-2xl font-bold text-center text-[#7C3AED] mb-1">
                        Đăng nhập FinSight
                    </h1>
                    <p className="text-center text-gray-600 text-sm mb-6">
                        Nền tảng phân tích, công cụ đầu tư chứng khoán trên máy
                        tính
                    </p>

                    <Form {...form}>
                        <form
                            onSubmit={form.handleSubmit(onSubmit)}
                            className="space-y-5"
                        >
                            <FormInput
                                control={form.control}
                                name="email"
                                label="Email"
                                placeholder="Nhập email..."
                            />
                            <FormInput
                                control={form.control}
                                name="password"
                                label="Mật khẩu"
                                placeholder="••••••••"
                                type="password"
                            />

                            {err && (
                                <p className="text-red-500 text-sm text-center font-medium">
                                    {err}
                                </p>
                            )}

                            <FormButton label="Đăng nhập" loading={loading} />

                            <div className="relative flex items-center justify-center">
                                <span className="absolute w-full h-[1px] bg-gradient-to-r from-transparent via-[#E0CCFF] to-transparent"></span>
                                <span className="relative bg-white/80 px-3 text-sm text-gray-500">
                                    hoặc
                                </span>
                            </div>

                            <div className="flex justify-center items-center mt-5 space-x-3">
                                {/* <SocialLoginButton
                                    href={`${API_BASE}/auth/google`}
                                    icon={<FaGoogle size={25} />}
                                    variant="google"
                                /> */}
                                <SocialLoginButton
                                    href={`${API_BASE}/auth/google`}
                                    icon={<FaGoogle size={25} />}
                                    variant="google"
                                />
                                {/* <SocialLoginButton
                                    href={`${API_BASE}/auth/facebook`}
                                    icon={<FaFacebook size={30} />}
                                    variant="facebook"
                                /> */}
                            </div>
                        </form>
                    </Form>

                    <p className="text-center text-sm text-gray-500 mt-6">
                        Chưa có tài khoản?{" "}
                        <Link
                            href="/register"
                            className="text-[#7C3AED] font-medium hover:underline"
                        >
                            Đăng ký ngay
                        </Link>
                    </p>
                </div>
            </div>
        </main>
    );
}

/** --- SOCIAL LOGIN BUTTON --- **/
function SocialLoginButton({
    href,
    icon,
    variant,
}: {
    href: string;
    icon: ReactNode;
    variant?: "google" | "facebook";
}) {
    return (
        <a
            href={href}
            className={cn(
                "w-12 h-12 flex items-center justify-center gap-2 rounded-full ",
                "border border-[#E0CCFF] bg-white/80 backdrop-blur-sm shadow-sm hover:shadow-[0_0_12px_rgba(147,51,234,0.15)] hover:scale-[1.03]",
                variant === "google"
                    ? "text-[#DB4437] hover:bg-[#FDE8E6]"
                    : "text-[#1877F2] hover:bg-[#E9F0FF]"
            )}
        >
            {icon}
        </a>
    );
}
