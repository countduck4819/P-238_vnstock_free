"use client";

import { ReactNode, useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";

import { Form } from "@/components/ui/form";
import { FormInput } from "@/share/components/FormInput";
import { FormButton } from "@/share/components/FormButtom";
import Link from "next/link";
import { Gender } from "@/store/users/user.reducer";
import { FormSelect } from "@/share/components/FormSelect";
import { UploadFileClient } from "@/share/components/UploadFileClient";
import { toast } from "react-toastify";

const registerSchema = z
    .object({
        username: z.string().min(3, "Tên đăng nhập tối thiểu 3 ký tự"),
        fullName: z.string().optional(),
        email: z.string().email("Email không hợp lệ"),
        password: z.string().min(6, "Mật khẩu tối thiểu 6 ký tự"),
        confirmPassword: z.string(),
        address: z.string().optional(),
        citizenId: z.string().optional(),
        gender: z.enum(Gender).optional(),
        avatar: z.string().optional(),
    })
    .refine((data) => data.password === data.confirmPassword, {
        message: "Mật khẩu xác nhận không khớp",
        path: ["confirmPassword"],
    });

type RegisterValues = z.infer<typeof registerSchema>;

export default function Register() {
    const router = useRouter();
    const [err, setErr] = useState("");

    const form = useForm<RegisterValues>({
        resolver: zodResolver(registerSchema),
        defaultValues: {
            username: "",
            email: "",
            fullName: "",
            password: "",
            confirmPassword: "",
            address: "",
            citizenId: "",
            gender: Gender.MALE,
            avatar: "",
        },
    });

    // --- Submit ---
    const onSubmit = async (values: RegisterValues) => {
        setErr("");
        try {
            const res = await fetch(
                `${process.env.NEXT_PUBLIC_API_BASE_URL}/users`,
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify(values),
                    credentials: "include",
                }
            );

            const data = await res.json();
            if (!data?.code)
                throw new Error(data?.message || "Đăng ký thất bại");

            toast.success("Tạo người dùng thành công!");
            setTimeout(() => router.push("/login"), 80);
        } catch (e: any) {
            setErr(e.message);
        }
    };

    const loading = form.formState.isSubmitting;

    return (
        <main className="min-h-screen flex items-center justify-center bg-gradient-to-br from-[#F9F5FF] to-[#F3E8FF] p-6">
            <div className="w-full max-w-md relative overflow-hidden rounded-2xl bg-white/70 backdrop-blur-xl border border-[#E0CCFF] shadow-[0_10px_30px_rgba(147,51,234,0.1)] animate-fadeIn">
                {/* background blur */}
                <div className="absolute inset-0 pointer-events-none">
                    <div className="absolute -top-32 left-10 w-72 h-72 bg-[#C084FC]/40 blur-3xl rounded-full animate-pulse"></div>
                    <div className="absolute -bottom-32 right-20 w-72 h-72 bg-[#7C3AED]/30 blur-3xl rounded-full animate-pulse delay-300"></div>
                </div>

                <div className="relative z-10 p-8">
                    <h1 className="text-2xl font-bold text-center text-[#7C3AED] mb-1">
                        Đăng ký tài khoản
                    </h1>

                    <p className="text-center text-gray-600 text-sm mb-6">
                        Tham gia FinSight để sử dụng toàn bộ tính năng phân tích
                    </p>

                    <Form {...form}>
                        <form
                            autoComplete="off"
                            onSubmit={form.handleSubmit(onSubmit)}
                            className="space-y-5"
                        >
                            <FormInput
                                name="username"
                                control={form.control}
                                label="Tên đăng nhập"
                            />
                            <FormInput
                                name="fullName"
                                control={form.control}
                                label="Họ tên"
                            />
                            <FormInput
                                name="email"
                                control={form.control}
                                label="Email"
                            />
                            <FormInput
                                name="citizenId"
                                control={form.control}
                                label="CMND/CCCD"
                            />
                            <FormInput
                                name="address"
                                control={form.control}
                                label="Địa chỉ"
                            />

                            {/* Gender Select */}
                            <FormSelect
                                name="gender"
                                control={form.control}
                                label="Giới tính"
                                options={[
                                    { label: "Nam", value: Gender.MALE },
                                    { label: "Nữ", value: Gender.FEMALE },
                                    { label: "Khác", value: Gender.OTHER },
                                ]}
                            />

                            {/* Avatar Upload – đẹp giống Login */}
                            <UploadFileClient
                                name="avatar"
                                label="Ảnh đại diện"
                                value={form.watch("avatar")}
                                onUploadComplete={(url) =>
                                    form.setValue("avatar", url)
                                }
                            />

                            <FormInput
                                name="password"
                                control={form.control}
                                label="Mật khẩu"
                                type="password"
                            />
                            <FormInput
                                name="confirmPassword"
                                control={form.control}
                                label="Xác nhận mật khẩu"
                                type="password"
                            />

                            {err && (
                                <p className="text-red-500 text-center text-sm">
                                    {err}
                                </p>
                            )}

                            <FormButton label="Đăng ký" loading={loading} />

                            <p className="text-center text-sm text-gray-500 mt-4">
                                Đã có tài khoản?{" "}
                                <Link
                                    href="/login"
                                    className="text-[#7C3AED] font-medium hover:underline"
                                >
                                    Đăng nhập ngay
                                </Link>
                            </p>
                        </form>
                    </Form>
                </div>
            </div>
        </main>
    );
}
