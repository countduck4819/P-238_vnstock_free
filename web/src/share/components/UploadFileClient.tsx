"use client";

import { useState } from "react";
import Image from "next/image";
import { API_BASE } from "@/utils/axiosInstance";

interface UploadFileProps {
    name: string;
    label?: string;
    value?: string;
    onUploadComplete: (url: string) => void;
}

export function UploadFileClient({
    name,
    label,
    value,
    onUploadComplete,
}: UploadFileProps) {
    const [preview, setPreview] = useState<string | null>(value || null);
    const [loading, setLoading] = useState(false);

    const handleUpload = async (file: File) => {
        const formData = new FormData();
        formData.append("avatar", file);

        setLoading(true);
        try {
            const res = await fetch(`${API_BASE}/upload/avatar`, {
                method: "POST",
                body: formData,
            });

            const data = await res.json();
            if (data?.data?.url) {
                setPreview(data.data.url);
                onUploadComplete(data.data.url);
            } else {
                alert("Upload thất bại");
            }
        } catch (err) {
            console.error("Upload error:", err);
            alert("Lỗi upload ảnh");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="w-full space-y-2">
            {label && (
                <p className="text-sm font-medium text-gray-700">{label}</p>
            )}

            <label className="
                relative 
                flex flex-col items-center justify-center 
                w-full h-40 
                rounded-xl cursor-pointer 
                border border-[#E0CCFF] bg-white/70 backdrop-blur-sm
                shadow-sm
                transition 
                hover:shadow-[0_0_12px_rgba(147,51,234,0.18)]
                hover:bg-white/90
            ">
                <input
                    type="file"
                    name={name}
                    autoComplete="off"
                    accept="image/*"
                    className="hidden"
                    onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) handleUpload(file);
                    }}
                />

                {loading ? (
                    <span className="text-[#7C3AED] animate-pulse text-sm">
                        Đang tải ảnh...
                    </span>
                ) : preview ? (
                    <Image
                        src={preview}
                        alt="preview"
                        width={300}
                        height={200}
                        className="
                            w-full h-full object-contain 
                            rounded-xl 
                            p-2
                        "
                    />
                ) : (
                    <div className="flex flex-col items-center text-gray-500">
                        <div className="
                            w-12 h-12 rounded-full 
                            bg-[#E0CCFF]/40 
                            flex items-center justify-center 
                            mb-2
                        ">
                            <span className="text-[#7C3AED] text-xl">⬆️</span>
                        </div>
                        <span className="text-sm">
                            Chọn ảnh đại diện
                        </span>
                    </div>
                )}
            </label>
        </div>
    );
}
