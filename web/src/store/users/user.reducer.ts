import { createSlice } from "@reduxjs/toolkit";

import {
    createUser,
    deleteUser,
    fetchUserDetail,
    fetchUsers,
    fetchUsersQuery,
    updateUser,
} from "./user.api";

export enum RoleGuard {
    USER = "user",
    ADMIN = "admin",
    FREE = "free",
    PREMIUM = "premium",
}

export enum AccountType {
    FREE = "free",
    PREMIUM = "premium",
}

export enum Gender {
    MALE = "male",
    FEMALE = "female",
    OTHER = "other",
}

export interface AdminUser {
    id: string;
    username: string;
    fullName?: string;
    email: string;
    role?: RoleGuard;
    accountType?: AccountType;
    gender?: Gender;
    avatar?: string;
}

interface Meta {
    page?: number;
    limit?: number;
    total?: number;
    totalPages?: number;
}

interface AdminUserState {
    list: AdminUser[];
    selected: AdminUser | null;
    loading: boolean;
    error: string | null;
    meta: Meta | null;
}

const initialState: AdminUserState = {
    list: [],
    selected: null,
    loading: false,
    error: null,
    meta: null,
};

export const userSlice = createSlice({
    name: "userSlice",
    initialState,
    reducers: {
        clearSelected: (state) => {
            state.selected = null;
        },
    },
    extraReducers: (builder) => {
        builder
            .addCase(fetchUsers.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(fetchUsers.fulfilled, (state, action) => {
                state.loading = false;
                state.list = action.payload;
            })
            .addCase(fetchUsers.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload as string;
            });

        builder
            .addCase(fetchUsersQuery.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(fetchUsersQuery.fulfilled, (state, action) => {
                state.loading = false;
                state.list = action.payload.data || [];
                state.meta = action.payload.meta || null;
            })
            .addCase(fetchUsersQuery.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload as string;
            });

        builder
            .addCase(fetchUserDetail.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(fetchUserDetail.fulfilled, (state, action) => {
                state.loading = false;
                state.selected = action.payload;
            })
            .addCase(fetchUserDetail.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload as string;
            });

        builder
            .addCase(createUser.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(createUser.fulfilled, (state, action) => {
                state.loading = false;
                state.list.unshift(action.payload);
            })
            .addCase(createUser.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload as string;
            });

        builder
            .addCase(updateUser.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(updateUser.fulfilled, (state, action) => {
                state.loading = false;
                const updated = action.payload;
                state.list = state.list.map((u) =>
                    u.id === updated.id ? updated : u
                );
                state.selected = updated;
            })
            .addCase(updateUser.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload as string;
            });

        builder
            .addCase(deleteUser.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(deleteUser.fulfilled, (state, action) => {
                state.loading = false;
                state.list = state.list.filter((u) => u.id !== action.payload);
            })
            .addCase(deleteUser.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload as string;
            });
    },
});

export const { clearSelected } = userSlice.actions;
export default userSlice.reducer;
