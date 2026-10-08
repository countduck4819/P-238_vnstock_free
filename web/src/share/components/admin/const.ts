import {
    LayoutDashboard,
    Users,
    FileText,
    Settings,
    LucideIcon,
    Layers3,
    BarChart3,
    Newspaper,
    TrendingUp,
    LineChart,
    PackageSearch,
} from "lucide-react";

export interface SidebarMenuItem {
    title: string;
    icon: LucideIcon | any;
    href?: string;
    children?: {
        title: string;
        href: string;
    }[];
}

export const sidebarMenu: SidebarMenuItem[] = [
    {
        title: "Dashboard",
        icon: LayoutDashboard,
        href: "/admin",
    },
    {
        title: "Quản lý tài khoản",
        icon: Users,
        href: "/admin/users",
    },
    {
        title: "Quản lý nhóm ngành",
        icon: BarChart3,
        href: "/admin/industries",
    },
    {
        title: "Quản lý cổ phiếu",
        icon: Layers3,
        href: "/admin/stocks",
    },
    {
        title: "Tin tức thị trường",
        icon: Newspaper,
        href: "/admin/news",
    },
    {
        title: "Quản lý khuyến nghị cổ phiếu",
        icon: TrendingUp,
        href: "/admin/stock-recommendations",
    },
    {
        title: "Cổ phiếu xu hướng tăng",
        icon: LineChart,
        href: "/admin/stock-prediction",
    },
    {
        title: "Quản lý đơn hàng",
        icon: PackageSearch,
        href: "/admin/premium-orders",
    },
    // {
    //     title: "Reports",
    //     icon: FileText,
    //     href: "/admin/reports",
    // },
    // {
    //     title: "Settings",
    //     icon: Settings,
    //     href: "/admin/settings",
    // },
];
