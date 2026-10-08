"use client";

import { Button } from "@/components/ui/button";
import { Edit, Trash2 } from "lucide-react";
import {
    AccountType,
    AdminUser,
    Gender,
    RoleGuard,
} from "@/store/users/user.reducer";
import { Column } from "@/share/components/admin/TableCustom";
import BadgeTag from "@/share/components/admin/Badge";
import Image from "next/image";
import { CrudField } from "@/share/components/admin/CrudDialog";

export const userColumns: Column<AdminUser>[] = [
    {
        key: "avatar",
        header: "Avatar",
        render: (item) => (
            <div className="flex justify-center">
                {item?.avatar && (
                    <Image
                        src={item.avatar}
                        alt={item.username}
                        width={40}
                        height={40}
                        className="w-[2rem] h-[2rem] rounded-[0.5rem] object-cover border border-gray-700"
                    />
                )}
            </div>
        ),
    },
    {
        key: "username",
        header: "Tên đăng nhập",
    },
    {
        key: "fullName",
        header: "Họ tên",
        render: (item) => item.fullName || "—",
    },
    {
        key: "email",
        header: "Email",
    },
    {
        key: "role",
        header: "Vai trò",
        render: (item) => {
            const role = item.role ?? RoleGuard.USER;
            const roleMap: Record<RoleGuard, { label: string; color: string }> =
                {
                    [RoleGuard.ADMIN]: {
                        label: "Quản trị viên",
                        color: "bg-red-500/20 text-red-400",
                    },
                    [RoleGuard.USER]: {
                        label: "Người dùng",
                        color: "bg-indigo-500/20 text-indigo-400",
                    },
                    [RoleGuard.FREE]: {
                        label: "Free",
                        color: "bg-gray-500/20 text-gray-300",
                    },
                    [RoleGuard.PREMIUM]: {
                        label: "Premium",
                        color: "bg-gradient-to-r from-[#6A5AF9]/30 to-[#FF5EDF]/30 text-[#FFDDEE] font-semibold shadow-[0_0_8px_rgba(255,94,223,0.4)]",
                    },
                };

            const { label, color } = roleMap[role];
            return <BadgeTag label={label} color={color} />;
        },
    },
    {
        key: "accountType",
        header: "Loại tài khoản",
        render: (item) => {
            const type = item.accountType ?? AccountType.FREE;
            const typeMap: Record<
                AccountType,
                { label: string; color: string }
            > = {
                [AccountType.FREE]: {
                    label: "Free",
                    color: "bg-gray-500/20 text-gray-300",
                },
                [AccountType.PREMIUM]: {
                    label: "Premium",
                    color: "bg-gradient-to-r from-[#6A5AF9]/30 to-[#FF5EDF]/30 text-[#FFDDEE] font-semibold shadow-[0_0_8px_rgba(255,94,223,0.4)]",
                },
            };

            const { label, color } = typeMap[type];
            return <BadgeTag label={label} color={color} />;
        },
    },
    {
        key: "gender",
        header: "Giới tính",
        render: (item) => {
            switch (item.gender) {
                case Gender.MALE:
                    return "Nam";
                case Gender.FEMALE:
                    return "Nữ";
                case Gender.OTHER:
                    return "Khác";
                default:
                    return "—";
            }
        },
    },
    {
        key: "actions",
        header: "Thao tác",
        render: (item, actions) => (
            <div className="flex items-center gap-2">
                <Button
                    size="icon"
                    variant="ghost"
                    type="button"
                    className="text-indigo-400 hover:text-indigo-300"
                    onClick={() => actions?.onEditClick?.(item)}
                >
                    <Edit className="h-4 w-4" />
                </Button>
                <Button
                    size="icon"
                    variant="ghost"
                    type="button"
                    className="text-red-400 hover:text-red-300"
                    onClick={() => actions?.onDeleteClick?.(item)}
                >
                    <Trash2 className="h-4 w-4" />
                </Button>
            </div>
        ),
    },
];

export const FieldCrud: CrudField[] = [
    { name: "username", label: "Tên đăng nhập", type: "input", required: true },
    {
        name: "email",
        label: "Email",
        type: "input",
        required: true,
        validate: (value) => {
            if (!value) return "Email là bắt buộc";
            if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value))
                return "Định dạng email không hợp lệ";
            return null;
        },
    },
    { name: "fullName", label: "Họ tên", type: "input" },
    { name: "address", label: "Địa chỉ", type: "textarea" },
    { name: "citizenId", label: "CMND/CCCD", type: "input" },

    {
        name: "password",
        label: "Mật khẩu",
        type: "password",
        required: true,
        validate: (value) => {
            if (!value) return "Mật khẩu là bắt buộc";
            if (value.length < 6) return "Mật khẩu phải có ít nhất 6 ký tự";
            return null;
        },
    },
    {
        name: "confirmPassword",
        label: "Xác nhận mật khẩu",
        type: "password",
        required: true,
        validate: (value, allValues) => {
            if (!value) return "Vui lòng nhập xác nhận mật khẩu";
            if (allValues?.password && value !== allValues?.password)
                return "Mật khẩu xác nhận không khớp";
            return null;
        },
    },

    {
        name: "gender",
        label: "Giới tính",
        type: "select",
        options: [
            { label: "Nam", value: Gender.MALE },
            { label: "Nữ", value: Gender.FEMALE },
            { label: "Khác", value: Gender.OTHER },
        ],
    },
    {
        name: "role",
        label: "Vai trò",
        type: "select",
        required: true,
        options: [
            { label: "Admin", value: RoleGuard.ADMIN },
            { label: "User", value: RoleGuard.USER },
            { label: "Free", value: RoleGuard.FREE },
            { label: "Premium", value: RoleGuard.PREMIUM },
        ],
    },
    {
        name: "accountType",
        label: "Loại tài khoản",
        type: "select",
        options: [
            { label: "Free", value: AccountType.FREE },
            { label: "Premium", value: AccountType.PREMIUM },
        ],
    },
    {
        name: "avatar",
        label: "Ảnh đại diện",
        type: "file",
        required: false,
    },
];
