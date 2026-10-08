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

export function UploadFile({
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
        <div className="space-y-3">
            <label
                className={`flex flex-col items-center justify-center w-full h-32 border-2 border-dashed rounded-xl cursor-pointer 
        ${
            preview
                ? "border-purple-500/40 bg-[#2a1b48]/60"
                : "border-purple-400/30 bg-[#21173B]/50"
        }
        hover:bg-[#2a1b48]/70 transition`}
            >
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
                    <span className="text-purple-400 animate-pulse">
                        Đang upload...
                    </span>
                ) : preview ? (
                    <Image
                        src={preview}
                        alt="preview"
                        width={100}
                        height={100}
                        className="rounded-lg h-full w-full object-contain border border-purple-600/40"
                    />
                ) : (
                    <span className="text-gray-300 text-sm">
                        📁 {label || "Chọn ảnh (PNG/JPG)"}
                    </span>
                )}
            </label>
        </div>
    );
}
