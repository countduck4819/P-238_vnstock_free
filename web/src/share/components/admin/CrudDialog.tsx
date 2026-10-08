// "use client";

// import { useEffect, useState, useMemo } from "react";
// import {
//     Dialog,
//     DialogContent,
//     DialogHeader,
//     DialogTitle,
//     DialogDescription,
//     DialogFooter,
// } from "@/components/ui/dialog";
// import {
//     AlertDialog,
//     AlertDialogContent,
//     AlertDialogHeader,
//     AlertDialogTitle,
//     AlertDialogDescription,
//     AlertDialogFooter,
//     AlertDialogCancel,
//     AlertDialogAction,
// } from "@/components/ui/alert-dialog";
// import { Button } from "@/components/ui/button";
// import { Input } from "@/components/ui/input";
// import {
//     Select,
//     SelectTrigger,
//     SelectValue,
//     SelectContent,
//     SelectItem,
// } from "@/components/ui/select";
// import { Textarea } from "@/components/ui/textarea";
// import { UploadFile } from "./UploadFile";
// import { Command, CommandEmpty, CommandInput, CommandItem, CommandList } from "@/components/ui/command";

// export interface CrudField {
//     name: string;
//     label: string;
//     type:
//         | "input"
//         | "select"
//         | "textarea"
//         | "file"
//         | "password"
//         | "number"
//         | "select-search";
//     options?: { label: string; value: string }[];
//     required?: boolean;
//     placeholder?: string;
//     validate?: (value: any, allValues?: Record<string, any>) => string | null;
// }

// interface CrudDialogProps<T> {
//     mode: "add" | "edit" | "delete" | null;
//     open: boolean;
//     onClose: () => void;
//     onSubmit: (data: Partial<T>, mode: "add" | "edit" | "delete") => void;
//     item?: T | null;
//     entityName?: string;
//     fields: CrudField[];
// }

// export function CrudDialog<T>({
//     mode,
//     open,
//     onClose,
//     onSubmit,
//     item,
//     entityName = "mục này",
//     fields,
// }: CrudDialogProps<T>) {
//     const [formData, setFormData] = useState<Partial<T>>({});
//     const [errors, setErrors] = useState<Record<string, string>>({});

//     const isEditMode = mode === "edit";

//     const dynamicFields = useMemo(
//         () =>
//             fields.map((f) =>
//                 ["password", "confirmPassword"].includes(f.name)
//                     ? { ...f, required: !isEditMode }
//                     : f
//             ),
//         [fields, isEditMode]
//     );

//     //  Khi mở dialog: load dữ liệu edit hoặc reset khi add
//     useEffect(() => {
//         if (mode === "edit" && item) {
//             setFormData(item);
//         } else if (mode === "add") {
//             setFormData({});
//         }
//     }, [mode, item]);

//     const handleChange = (key: string, value: string) => {
//         setFormData((prev) => ({ ...prev, [key]: value }));
//         setErrors((prev) => ({ ...prev, [key]: "" }));
//     };

//     const validateForm = () => {
//         const newErrors: Record<string, string> = {};

//         dynamicFields.forEach((f) => {
//             const value = (formData as any)[f.name];

//             if (f.required && (value === undefined || value === "")) {
//                 newErrors[f.name] = `${f.label} là bắt buộc`;
//             }

//             if (f.validate) {
//                 const msg = f.validate(value, formData as any);
//                 if (msg) newErrors[f.name] = msg;
//             }
//         });

//         setErrors(newErrors);
//         return Object.keys(newErrors).length === 0;
//     };

//     if (mode === "add" || mode === "edit") {
//         return (
//             <Dialog open={open} onOpenChange={onClose}>
//                 <DialogContent
//                     className="bg-gradient-to-br from-[#1A1034] via-[#21173F] to-[#2A1B47]
//           border border-purple-600/30 shadow-xl shadow-purple-900/30
//           text-gray-100 max-w-lg max-h-[85vh] overflow-y-auto rounded-2xl p-6"
//                 >
//                     <form
//                         autoComplete="off"
//                         onSubmit={(e) => {
//                             e.preventDefault();
//                             if (!validateForm()) return;
//                             onSubmit(formData, mode);
//                             onClose();
//                         }}
//                         className="space-y-4 py-3"
//                     >
//                         {/* Ngăn Chrome autofill linh tinh */}
//                         <input
//                             type="text"
//                             name="fake-user"
//                             autoComplete="username"
//                             style={{ display: "none" }}
//                         />
//                         <input
//                             type="password"
//                             name="fake-pass"
//                             autoComplete="new-password"
//                             style={{ display: "none" }}
//                         />

//                         <DialogHeader>
//                             <DialogTitle className="text-lg font-semibold text-white">
//                                 {isEditMode
//                                     ? `Chỉnh sửa ${entityName}`
//                                     : `Thêm ${entityName} mới`}
//                             </DialogTitle>
//                             <DialogDescription className="text-gray-400">
//                                 {isEditMode
//                                     ? `Cập nhật thông tin ${entityName} đã chọn.`
//                                     : `Điền thông tin ${entityName} mới vào form bên dưới.`}
//                             </DialogDescription>
//                         </DialogHeader>

//                         {dynamicFields.map((field) => (
//                             <div key={field.name}>
//                                 <label className="block text-sm text-gray-300 mb-1">
//                                     {field.label}
//                                     {field.required && (
//                                         <span className="text-red-400 ml-1">
//                                             *
//                                         </span>
//                                     )}
//                                 </label>
//                                 {(field.type === "input" ||
//                                     field.type === "password") && (
//                                     <Input
//                                         name={`field-${field.name}`}
//                                         autoComplete="off"
//                                         type={
//                                             field.type === "password"
//                                                 ? "password"
//                                                 : "text"
//                                         }
//                                         placeholder={
//                                             field.placeholder || field.label
//                                         }
//                                         value={
//                                             (formData as any)[field.name] || ""
//                                         }
//                                         onChange={(e) =>
//                                             handleChange(
//                                                 field.name,
//                                                 e.target.value
//                                             )
//                                         }
//                                         className={`w-full bg-[#21173B]/70 border ${
//                                             errors[field.name]
//                                                 ? "border-red-400"
//                                                 : "border-purple-500/40"
//                                         } text-white rounded-md`}
//                                     />
//                                 )}
//                                 {field.type === "textarea" && (
//                                     <Textarea
//                                         name={`field-${field.name}`}
//                                         autoComplete="off"
//                                         rows={3}
//                                         placeholder={
//                                             field.placeholder || field.label
//                                         }
//                                         value={
//                                             (formData as any)[field.name] || ""
//                                         }
//                                         onChange={(e) =>
//                                             handleChange(
//                                                 field.name,
//                                                 e.target.value
//                                             )
//                                         }
//                                         className={`w-full bg-[#21173B]/70 border ${
//                                             errors[field.name]
//                                                 ? "border-red-400"
//                                                 : "border-purple-500/40"
//                                         } text-white rounded-md resize-none`}
//                                     />
//                                 )}
//                                 {field.type === "select" && (
//                                     <Select
//                                         value={
//                                             (formData as any)[
//                                                 field.name
//                                             ]?.toString() || ""
//                                         }
//                                         onValueChange={(v) =>
//                                             handleChange(field.name, v)
//                                         }
//                                     >
//                                         <SelectTrigger
//                                             className={`w-full h-10 bg-[#21173B]/70 border ${
//                                                 errors[field.name]
//                                                     ? "border-red-400"
//                                                     : "border-purple-500/40"
//                                             } text-gray-100 rounded-md`}
//                                         >
//                                             <SelectValue
//                                                 placeholder={
//                                                     field.placeholder ||
//                                                     `Chọn ${field.label}`
//                                                 }
//                                             />
//                                         </SelectTrigger>
//                                         <SelectContent className="bg-[#1E1538] border border-purple-600/40 text-gray-100 shadow-xl backdrop-blur-sm">
//                                             {field.options?.map((opt) => (
//                                                 <SelectItem
//                                                     key={opt.value}
//                                                     value={opt.value}
//                                                     className="hover:bg-purple-700/30 cursor-pointer text-gray-200"
//                                                 >
//                                                     {opt.label}
//                                                 </SelectItem>
//                                             ))}
//                                         </SelectContent>
//                                     </Select>
//                                 )}
//                                 {field.type === "file" && (
//                                     <UploadFile
//                                         name={field.name}
//                                         label={field.label}
//                                         value={
//                                             (formData as any)[
//                                                 field.name
//                                             ] as string
//                                         }
//                                         onUploadComplete={(url) => {
//                                             setFormData((prev) => ({
//                                                 ...prev,
//                                                 [field.name]: url as any,
//                                             }));
//                                             setErrors((prev) => ({
//                                                 ...prev,
//                                                 [field.name]: "",
//                                             }));
//                                         }}
//                                     />
//                                 )}
//                                 {field.type === "number" && (
//                                     <Input
//                                         type="number"
//                                         step="any"
//                                         placeholder={
//                                             field.placeholder || field.label
//                                         }
//                                         value={
//                                             (formData as any)[field.name] || ""
//                                         }
//                                         onChange={(e) =>
//                                             handleChange(
//                                                 field.name,
//                                                 e.target.value
//                                             )
//                                         }
//                                         className={`w-full bg-[#21173B]/70 border ${
//                                             errors[field.name]
//                                                 ? "border-red-400"
//                                                 : "border-purple-500/40"
//                                         } text-white rounded-md`}
//                                     />
//                                 )}

//                                 {field.type === "select-search" && (
//                                     <div className="relative">
//                                         <Command>
//                                             <CommandInput placeholder="Tìm kiếm..." />
//                                             <CommandList>
//                                                 {field.options?.length ? (
//                                                     field.options.map((opt) => (
//                                                         <CommandItem
//                                                             key={opt.value}
//                                                             onSelect={() =>
//                                                                 handleChange(
//                                                                     field.name,
//                                                                     opt.value
//                                                                 )
//                                                             }
//                                                             className="cursor-pointer hover:bg-purple-700/40 text-gray-100"
//                                                         >
//                                                             {opt.label}
//                                                         </CommandItem>
//                                                     ))
//                                                 ) : (
//                                                     <CommandEmpty>
//                                                         Không có dữ liệu
//                                                     </CommandEmpty>
//                                                 )}
//                                             </CommandList>
//                                         </Command>
//                                     </div>
//                                 )}
//                                 {errors[field.name] && (
//                                     <p className="text-xs text-red-400 mt-1">
//                                         {errors[field.name]}
//                                     </p>
//                                 )}
//                             </div>
//                         ))}

//                         <DialogFooter>
//                             <Button
//                                 variant="ghost"
//                                 type="button"
//                                 onClick={onClose}
//                             >
//                                 Hủy
//                             </Button>
//                             <Button
//                                 type="submit"
//                                 className="bg-gradient-to-r from-[#6A5AF9] to-[#FF5EDF] text-white shadow-[0_0_12px_rgba(255,94,223,0.4)]"
//                             >
//                                 {isEditMode ? "Lưu thay đổi" : "Thêm mới"}
//                             </Button>
//                         </DialogFooter>
//                     </form>
//                 </DialogContent>
//             </Dialog>
//         );
//     }

//     // Xác nhận xóa
//     if (mode === "delete" && item) {
//         return (
//             <AlertDialog open={open} onOpenChange={onClose}>
//                 <AlertDialogContent className="bg-gradient-to-br from-[#1A1034] to-[#2A1B47] border border-red-600/30 shadow-lg shadow-red-900/30 text-gray-100">
//                     <AlertDialogHeader>
//                         <AlertDialogTitle className="text-lg text-red-400">
//                             Xác nhận xóa {entityName}
//                         </AlertDialogTitle>
//                         <AlertDialogDescription className="text-gray-300">
//                             Bạn có chắc muốn xóa{" "}
//                             <span className="text-white font-semibold">
//                                 {(item as any).name ||
//                                     (item as any).fullName ||
//                                     "mục này"}
//                             </span>
//                             ? Hành động này không thể hoàn tác.
//                         </AlertDialogDescription>
//                     </AlertDialogHeader>
//                     <AlertDialogFooter>
//                         <AlertDialogCancel className="bg-[#1E153A] text-gray-300 border border-gray-600/30 hover:bg-gray-800">
//                             Hủy
//                         </AlertDialogCancel>
//                         <AlertDialogAction
//                             className="bg-red-600 hover:bg-red-700 text-white shadow-[0_0_10px_rgba(255,0,0,0.4)]"
//                             onClick={() => {
//                                 onSubmit(item, "delete");
//                                 onClose();
//                             }}
//                         >
//                             Xóa
//                         </AlertDialogAction>
//                     </AlertDialogFooter>
//                 </AlertDialogContent>
//             </AlertDialog>
//         );
//     }

//     return null;
// }
"use client";

import { useEffect, useState, useMemo, memo, useCallback } from "react";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
    DialogFooter,
} from "@/components/ui/dialog";
import {
    AlertDialog,
    AlertDialogContent,
    AlertDialogHeader,
    AlertDialogTitle,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogCancel,
    AlertDialogAction,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
    Select,
    SelectTrigger,
    SelectValue,
    SelectContent,
    SelectItem,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { UploadFile } from "./UploadFile";
import { ChevronDown } from "lucide-react";

export interface CrudField {
    name: string;
    label: string;
    type:
        | "input"
        | "select"
        | "textarea"
        | "file"
        | "password"
        | "number"
        | "select-search";
    options?: { label: string; value: string }[];
    required?: boolean;
    placeholder?: string;
    validate?: (value: any, allValues?: Record<string, any>) => string | null;
    hidden?: boolean;
    /** 🔹 Callback khi chọn option (dành riêng cho select-search, auto fill giá, v.v.) */
    onSelect?: (
        value: string,
        updateForm: (values: Record<string, any>) => void
    ) => void;
    disabled?: boolean;
}

interface CrudDialogProps<T> {
    mode: "add" | "edit" | "delete" | null;
    open: boolean;
    onClose: () => void;
    onSubmit: (data: Partial<T>, mode: "add" | "edit" | "delete") => void;
    item?: T | null;
    entityName?: string;
    fields: CrudField[];
}

export function CrudDialog<T>({
    mode,
    open,
    onClose,
    onSubmit,
    item,
    entityName = "mục này",
    fields,
}: CrudDialogProps<T>) {
    const [formData, setFormData] = useState<Partial<T>>({});
    const [errors, setErrors] = useState<Record<string, string>>({});

    const isEditMode = mode === "edit";

    const dynamicFields = useMemo(() => {
        return fields.map((f) => {
            // ❌ Ẩn field "Mã cổ phiếu" khi đang edit
            if (isEditMode && f.name === "stockId") {
                return { ...f, hidden: true };
            }
            if (["password", "confirmPassword"].includes(f.name)) {
                return { ...f, required: !isEditMode };
            }
            return f;
        });
    }, [fields, isEditMode]);

    useEffect(() => {
        if (mode === "edit" && item) setFormData(item);
        else if (mode === "add") setFormData({});
    }, [mode, item]);

    const handleChange = useCallback((key: string, value: string) => {
        setFormData((prev) => {
            if (prev[key as keyof typeof prev] === value) return prev;
            return { ...prev, [key]: value };
        });
        setErrors((prev) => ({ ...prev, [key]: "" }));
    }, []);

    const validateForm = () => {
        const newErrors: Record<string, string> = {};
        dynamicFields.forEach((f) => {
            const value = (formData as any)[f.name];
            if (f.required && (value === undefined || value === ""))
                newErrors[f.name] = `${f.label} là bắt buộc`;
            if (f.validate) {
                const msg = f.validate(value, formData as any);
                if (msg) newErrors[f.name] = msg;
            }

            if (["buyPrice", "targetPrice", "stopLossPrice"].includes(f.name)) {
                const v = parseFloat(value || "0");
                if (v <= 0) newErrors[f.name] = `${f.label} phải lớn hơn 0`;

                const buy = parseFloat((formData as any).buyPrice || "0");

                if (f.name === "targetPrice" && buy && v < buy)
                    newErrors[f.name] = "Giá chốt lời phải ≥ giá mua";

                if (f.name === "stopLossPrice" && buy && v > buy)
                    newErrors[f.name] = "Giá cắt lỗ phải ≤ giá mua";
            }
        });
        setErrors(newErrors);
        return Object.keys(newErrors).length === 0;
    };

    if (mode === "add" || mode === "edit") {
        return (
            <Dialog open={open} onOpenChange={onClose}>
                <DialogContent
                    className="bg-gradient-to-br from-[#1A1034] via-[#21173F] to-[#2A1B47]
            border border-purple-600/30 shadow-xl shadow-purple-900/30
            text-gray-100 max-w-lg max-h-[85vh] overflow-y-auto rounded-2xl p-6"
                >
                    <DialogHeader>
                        <DialogTitle className="text-lg font-semibold text-white">
                            {isEditMode
                                ? `Chỉnh sửa ${entityName}`
                                : `Thêm ${entityName} mới`}
                        </DialogTitle>
                        <DialogDescription className="text-gray-400">
                            {isEditMode
                                ? `Cập nhật thông tin ${entityName} đã chọn.`
                                : `Điền thông tin ${entityName} mới vào form bên dưới.`}
                        </DialogDescription>
                    </DialogHeader>

                    <form
                        autoComplete="off"
                        onSubmit={(e) => {
                            e.preventDefault();
                            if (!validateForm()) return;
                            const numericForm = { ...formData };
                            [
                                "buyPrice",
                                "targetPrice",
                                "stopLossPrice",
                                "stockId",
                            ].forEach((key) => {
                                if (
                                    numericForm[
                                        key as keyof typeof numericForm
                                    ] !== undefined
                                ) {
                                    numericForm[
                                        key as keyof typeof numericForm
                                    ] = Number(
                                        numericForm[
                                            key as keyof typeof numericForm
                                        ]
                                    ) as any;
                                }
                            });

                            onSubmit(numericForm, mode);
                            onClose();
                        }}
                        className="space-y-4 py-3"
                    >
                        {dynamicFields
                            .filter((f) => !f.hidden) // 👈 Bỏ qua field ẩn
                            .map((f) => (
                                <MemoField
                                    key={f.name}
                                    field={f}
                                    value={(formData as any)[f.name] || ""}
                                    error={errors[f.name]}
                                    onChange={(v) => handleChange(f.name, v)}
                                    updateForm={(values) =>
                                        setFormData((prev) => ({
                                            ...prev,
                                            ...values,
                                        }))
                                    }
                                    allValues={formData as Record<string, any>}
                                />
                            ))}

                        <DialogFooter>
                            <Button
                                variant="ghost"
                                type="button"
                                onClick={onClose}
                            >
                                Hủy
                            </Button>
                            <Button
                                type="submit"
                                className="bg-gradient-to-r from-[#6A5AF9] to-[#FF5EDF] text-white shadow-[0_0_12px_rgba(255,94,223,0.4)]"
                            >
                                {isEditMode ? "Lưu thay đổi" : "Thêm mới"}
                            </Button>
                        </DialogFooter>
                    </form>
                </DialogContent>
            </Dialog>
        );
    }

    if (mode === "delete" && item)
        return (
            <AlertDialog open={open} onOpenChange={onClose}>
                <AlertDialogContent className="bg-gradient-to-br from-[#1A1034] to-[#2A1B47] border border-red-600/30 shadow-lg shadow-red-900/30 text-gray-100">
                    <AlertDialogHeader>
                        <AlertDialogTitle className="text-lg text-red-400">
                            Xác nhận xóa {entityName}
                        </AlertDialogTitle>
                        <AlertDialogDescription className="text-gray-300">
                            Bạn có chắc muốn xóa{" "}
                            <span className="text-white font-semibold">
                                {(item as any).name ||
                                    (item as any).fullName ||
                                    "mục này"}
                            </span>
                            ? Hành động này không thể hoàn tác.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel className="bg-[#1E153A] text-gray-300 border border-gray-600/30 hover:bg-gray-800">
                            Hủy
                        </AlertDialogCancel>
                        <AlertDialogAction
                            className="bg-red-600 hover:bg-red-700 text-white shadow-[0_0_10px_rgba(255,0,0,0.4)]"
                            onClick={() => {
                                onSubmit(item, "delete");
                                onClose();
                            }}
                        >
                            Xóa
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        );

    return null;
}

/* -------- 🧩 Field riêng: giảm re-render + nhẹ hơn -------- */
const MemoField = memo(function MemoField({
    field,
    value,
    error,
    onChange,
    updateForm,
    allValues,
}: {
    field: CrudField;
    value: any;
    error?: string;
    onChange: (v: any) => void;
    updateForm?: (values: Record<string, any>) => void;
    allValues?: Record<string, any>;
}) {
    const base =
        "w-full bg-[#21173B]/70 border text-white rounded-md " +
        (error ? "border-red-400" : "border-purple-500/40");

    if (field.type === "input" || field.type === "password")
        return (
            <div>
                <label className="block text-sm text-gray-300 mb-1">
                    {field.label}
                    {field.required && (
                        <span className="text-red-400 ml-1">*</span>
                    )}
                </label>
                <Input
                    disabled={field.disabled}
                    type={field.type === "password" ? "password" : "text"}
                    placeholder={field.placeholder || field.label}
                    value={value}
                    onChange={(e) => onChange(e.target.value)}
                    className={base}
                />
                {error && <p className="text-xs text-red-400 mt-1">{error}</p>}
            </div>
        );

    if (field.type === "number") {
        const buyPrice = parseFloat(
            ((allValues?.buyPrice ?? "") as any).toString() || "0"
        );
        const thisValue = parseFloat(((value ?? "") as any).toString() || "0");

        const showPct =
            ["targetPrice", "stopLossPrice"].includes(field.name) && !!buyPrice;
        const diff = showPct ? ((thisValue - buyPrice) / buyPrice) * 100 : 0;

        const color =
            diff > 0
                ? "text-green-400"
                : diff < 0
                ? "text-red-400"
                : "text-gray-400";

        const handleInput = (e: React.ChangeEvent<HTMLInputElement>) => {
            let val = e.target.value;

            if (val.startsWith("-") || val === "0") return;

            const num = parseFloat(val || "0");

            if (field.name === "targetPrice" && buyPrice && num < buyPrice)
                return;
            if (field.name === "stopLossPrice" && buyPrice && num > buyPrice)
                return;

            onChange(val);
        };

        return (
            <div className="w-full">
                <label className="block text-sm text-gray-300 mb-1">
                    {field.label}
                </label>
                <div className="relative w-full">
                    <input
                        disabled={field.disabled}
                        type="number"
                        step="any"
                        value={value}
                        onChange={handleInput}
                        placeholder={field.placeholder || field.label}
                        className={`${base} w-full h-10 px-3 pr-12 
            [appearance:textfield] 
            [&::-webkit-inner-spin-button]:appearance-none 
            [&::-webkit-outer-spin-button]:appearance-none`}
                    />
                    {showPct && (
                        <span
                            className={`absolute right-3 top-1/2 -translate-y-1/2 text-xs font-medium ${color}`}
                        >
                            {diff > 0 ? "+" : ""}
                            {diff.toFixed(1)}%
                        </span>
                    )}
                </div>
                {error && <p className="text-xs text-red-400 mt-1">{error}</p>}
            </div>
        );
    }

    if (field.type === "textarea")
        return (
            <div>
                <label className="block text-sm text-gray-300 mb-1">
                    {field.label}
                </label>
                <Textarea
                    disabled={field.disabled}
                    rows={3}
                    value={value}
                    onChange={(e) => onChange(e.target.value)}
                    className={`${base} resize-none`}
                />
                {error && <p className="text-xs text-red-400 mt-1">{error}</p>}
            </div>
        );

    if (field.type === "select")
        return (
            <div>
                <label className="block text-sm text-gray-300 mb-1">
                    {field.label}
                </label>
                <Select
                    disabled={field.disabled}
                    value={value?.toString() || ""}
                    onValueChange={onChange}
                >
                    <SelectTrigger className={`${base} h-10 text-gray-100`}>
                        <SelectValue
                            placeholder={
                                field.placeholder || `Chọn ${field.label}`
                            }
                        />
                    </SelectTrigger>
                    <SelectContent className="bg-[#1E1538] border border-purple-600/40 text-gray-100 shadow-xl backdrop-blur-sm">
                        {field.options?.map((opt) => (
                            <SelectItem
                                key={opt.value}
                                value={opt.value}
                                className="hover:bg-purple-700/30 cursor-pointer text-gray-200"
                            >
                                {opt.label}
                            </SelectItem>
                        ))}
                    </SelectContent>
                </Select>
                {error && <p className="text-xs text-red-400 mt-1">{error}</p>}
            </div>
        );

    if (field.type === "select-search") {
        const [open, setOpen] = useState(false);
        const [query, setQuery] = useState("");
        const selectedOpt = field.options?.find((o) => o.value === value);
        const filtered =
            field.options?.filter((o) =>
                o.label.toLowerCase().includes(query.toLowerCase())
            ) || [];

        return (
            <div className="relative">
                <label className="block text-sm text-gray-300 mb-1">
                    {field.label}
                    {field.required && (
                        <span className="text-red-400 ml-1">*</span>
                    )}
                </label>

                {/* Trigger */}
                <button
                    type="button"
                    onClick={() => setOpen(!open)}
                    className={`w-full h-10 px-3 flex items-center justify-between 
        bg-[#21173B]/70 border ${
            error ? "border-red-400" : "border-purple-500/40"
        } text-gray-100 rounded-md`}
                >
                    <span className={selectedOpt ? "" : "text-gray-400"}>
                        {selectedOpt?.label || field.placeholder || "Chọn..."}
                    </span>
                    <ChevronDown className="w-4 h-4 opacity-70" />
                </button>

                {/* Dropdown (render ngay trong DOM, không Portal) */}
                {open && (
                    <div
                        className="absolute z-[1001] mt-1 w-full bg-[#1E1538] border 
          border-purple-600/40 text-gray-100 rounded-lg shadow-xl 
          backdrop-blur-sm max-h-60 overflow-y-auto animate-in fade-in"
                    >
                        <div className="p-2 border-b border-purple-700/30">
                            <input
                                type="text"
                                placeholder="Tìm kiếm..."
                                value={query}
                                onChange={(e) => setQuery(e.target.value)}
                                className="w-full px-2 py-1.5 text-sm bg-transparent 
              text-gray-100 placeholder:text-gray-400 border border-purple-700/30 
              rounded focus:outline-none"
                            />
                        </div>

                        {filtered.length > 0 ? (
                            filtered.map((opt) => (
                                <div
                                    key={opt.value}
                                    onClick={() => {
                                        onChange(opt.value);
                                        if (field.onSelect && updateForm) {
                                            field.onSelect(
                                                opt.value,
                                                updateForm
                                            );
                                        }
                                        setOpen(false);
                                    }}
                                    className={`px-3 py-2 cursor-pointer text-sm hover:bg-purple-700/40 ${
                                        opt.value === value
                                            ? "bg-purple-700/30"
                                            : ""
                                    }`}
                                >
                                    {opt.label}
                                </div>
                            ))
                        ) : (
                            <div className="px-3 py-2 text-sm text-gray-400">
                                Không có dữ liệu
                            </div>
                        )}
                    </div>
                )}

                {error && <p className="text-xs text-red-400 mt-1">{error}</p>}
            </div>
        );
    }

    if (field.type === "file")
        return (
            <UploadFile
                name={field.name}
                label={field.label}
                value={value}
                onUploadComplete={(url) => onChange(url)}
            />
        );

    return null;
});
