"use client";

import {
    FormField,
    FormItem,
    FormLabel,
    FormMessage,
} from "@/components/ui/form";
import {
    Select,
    SelectTrigger,
    SelectContent,
    SelectValue,
    SelectItem,
} from "@/components/ui/select";
import { Control, FieldValues, Path } from "react-hook-form";
import { cn } from "@/lib/utils";

interface FormSelectProps<T extends FieldValues> {
    control: Control<T>;
    name: Path<T>;
    label?: string;
    placeholder?: string;
    options: { label: string; value: string }[];
    className?: string;
}

export function FormSelect<T extends FieldValues>({
    control,
    name,
    label,
    placeholder,
    options,
    className,
}: FormSelectProps<T>) {
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

                    <Select onValueChange={field.onChange} value={field.value}>
                        <SelectTrigger
                            className={cn(
                                "flex h-11 w-full items-center justify-between rounded-xl border border-[#E0CCFF] bg-white/70",
                                "backdrop-blur-sm px-4 text-[15px] text-gray-800",
                                "shadow-[0_2px_6px_rgba(147,51,234,0.08)] transition-all duration-300",
                                "hover:border-[#C084FC] focus-visible:border-[#9333EA] focus-visible:shadow-[0_0_0_3px_rgba(147,51,234,0.25)]",
                                "focus-visible:outline-none focus-visible:ring-0",
                                "disabled:cursor-not-allowed disabled:opacity-60",
                                className
                            )}
                        >
                            <SelectValue
                                placeholder={placeholder}
                                className="text-gray-500"
                            />
                        </SelectTrigger>

                        <SelectContent
                            className={cn(
                                "rounded-xl border border-[#EADFFF] bg-white/95",
                                "shadow-[0_4px_18px_rgba(147,51,234,0.15)] backdrop-blur-sm",
                                "overflow-hidden animate-fadeIn"
                            )}
                        >
                            {options.map((opt) => (
                                <SelectItem
                                    key={opt.value}
                                    value={opt.value}
                                    className={cn(
                                        "cursor-pointer px-4 py-2.5 text-[15px] text-gray-700 transition-all",
                                        "hover:bg-[#F5E8FF] hover:text-[#6B21A8]",
                                        "focus:bg-[#EADFFF] focus:text-[#6B21A8]",
                                        "data-[state=checked]:bg-[#EADFFF] data-[state=checked]:text-[#6B21A8]"
                                    )}
                                >
                                    {opt.label}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>

                    <FormMessage className="text-red-500 text-sm" />
                </FormItem>
            )}
        />
    );
}
