"use client";

import { useEffect, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { toast } from "react-toastify";
import {
    createUser,
    deleteUser,
    fetchUsersQuery,
    updateUser,
} from "@/store/users/user.api";
import { AppDispatch, RootState } from "@/redux/store";
import { TableCustom } from "@/share/components/admin/TableCustom";
import { FieldCrud, userColumns } from "./const";
import { CrudDialog } from "@/share/components/admin/CrudDialog";
import { AdminUser } from "@/store/users/user.reducer";

export default function AdminUsersPage() {
    const dispatch = useDispatch<AppDispatch>();
    const {
        list: users,
        meta,
        loading,
    } = useSelector((state: RootState) => state.usersReducer);

    const [page, setPage] = useState(1);
    const [limit, setLimit] = useState(10);
    const [filters, setFilters] = useState<Record<string, string>>({});

    const [dialog, setDialog] = useState<{
        open: boolean;
        mode: "add" | "edit" | "delete" | null;
        item?: AdminUser | null;
    }>({
        open: false,
        mode: null,
        item: null,
    });

    useEffect(() => {
        dispatch(fetchUsersQuery({ page, limit, filters }));
    }, [dispatch, page, limit, filters]);

    const handleAdd = () => setDialog({ open: true, mode: "add", item: null });
    const handleEdit = (user: AdminUser) =>
        setDialog({ open: true, mode: "edit", item: user });
    const handleDelete = (user: AdminUser) =>
        setDialog({ open: true, mode: "delete", item: user });

    const handleSubmit = async (
        data: Partial<AdminUser>,
        mode: "add" | "edit" | "delete"
    ) => {
        try {
            if (mode === "add") {
                await dispatch(createUser(data as any)).unwrap();
                toast.success("Tạo người dùng thành công!");
            } else if (mode === "edit") {
                await dispatch(
                    updateUser({ id: data?.id as string, data })
                ).unwrap();
                toast.success("Cập nhật người dùng thành công!");
            } else if (mode === "delete") {
                await dispatch(deleteUser(data.id as string)).unwrap();
                toast.success("Xoá người dùng thành công!");
            }

            setDialog({ open: false, mode: null });
            dispatch(fetchUsersQuery({ page, limit, filters }));
        } catch (error: any) {
            toast.error(error || "Thao tác thất bại, vui lòng thử lại");
        }
    };

    return (
        <>
            <div className="p-6 w-full shadow-lg shadow-purple-900/30 h-full">
                <h2
                    className="text-[1.5rem] md:text-3xl font-semibold 
  bg-gradient-to-r from-[#6A5AF9] to-[#FF5EDF] 
  bg-clip-text text-transparent tracking-tight mb-8"
                >
                    Quản lý tài khoản
                </h2>
                <TableCustom
                    columns={userColumns}
                    data={users}
                    meta={meta}
                    loading={loading}
                    searchConfig={[
                        { key: "username", label: "Tên đăng nhập" },
                        { key: "email", label: "Email" },
                    ]}
                    onAddClick={handleAdd}
                    onEditClick={handleEdit}
                    onDeleteClick={handleDelete}
                    onPageChange={setPage}
                    onLimitChange={setLimit}
                    onFilterChange={setFilters}
                />
            </div>

            <CrudDialog
                open={dialog.open}
                mode={dialog.mode}
                item={dialog.item}
                entityName="người dùng"
                onClose={() => setDialog({ open: false, mode: null })}
                onSubmit={handleSubmit}
                fields={FieldCrud}
            />
        </>
    );
}
