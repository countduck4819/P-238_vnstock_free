"use client";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface FormButtonProps {
    label: string;
    loading?: boolean;
    className?: string;
}

export function FormButton({ label, loading, className }: FormButtonProps) {
    return (
        <Button
            type="submit"
            disabled={loading}
            className={cn(
                "cursor-pointer w-full rounded-full bg-gradient-to-r from-[#7C3AED] via-[#9333EA] to-[#C084FC]",
                "text-white font-semibold py-2.5 text-[15px] shadow-[0_4px_15px_rgba(147,51,234,0.25)]",
                "hover:shadow-[0_6px_20px_rgba(147,51,234,0.35)] hover:scale-[1.03] transition-all duration-300",
                className
            )}
        >
            {loading ? "Đang xử lý..." : label}
        </Button>
    );
}
