"use client";

import { Input } from "@/components/ui/input";
import {
    FormField,
    FormItem,
    FormLabel,
    FormMessage,
} from "@/components/ui/form";
import { Control, FieldValues, Path } from "react-hook-form";
import { cn } from "@/lib/utils";

interface FormInputProps<T extends FieldValues> {
    control: Control<T>;
    name: Path<T>;
    label?: string;
    placeholder?: string;
    type?: string;
    className?: string;
}

export function FormInput<T extends FieldValues>({
    control,
    name,
    label,
    placeholder,
    type = "text",
    className,
}: FormInputProps<T>) {
    return (
        <FormField
            control={control}
            name={name}
            render={({ field }) => (
                <FormItem className="space-y-1.5">
                    {label && (
                        <FormLabel className="text-sm font-medium text-gray-700">
                            {label}
                        </FormLabel>
                    )}
                    <Input
                        {...field}
                        type={type}
                        placeholder={placeholder}
                        className={cn(
                            "h-11 w-full rounded-xl border border-[#E0CCFF] bg-white/70 backdrop-blur-sm",
                            "px-4 text-[15px] text-gray-800 placeholder:text-gray-400 shadow-[0_2px_6px_rgba(147,51,234,0.08)]",
                            "hover:border-[#C084FC]",
                            "focus-visible:outline-none focus-visible:ring-0 focus-visible:border-[#9333EA] focus-visible:shadow-[0_0_0_3px_rgba(147,51,234,0.25)]",
                            "transition-all duration-300",
                            "disabled:cursor-not-allowed disabled:opacity-60",
                            className
                        )}
                    />
                    <FormMessage className="text-red-500 text-sm" />
                </FormItem>
            )}
        />
    );
}
