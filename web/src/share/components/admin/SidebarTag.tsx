"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
    Sidebar,
    SidebarContent,
    SidebarGroup,
    SidebarGroupLabel,
    SidebarGroupContent,
    SidebarMenu,
    SidebarMenuItem,
    SidebarMenuButton,
    SidebarMenuSub,
    SidebarMenuSubItem,
    useSidebar,
} from "@/components/ui/sidebar";
import {
    Collapsible,
    CollapsibleTrigger,
    CollapsibleContent,
} from "@/components/ui/collapsible";
import { ChevronRight } from "lucide-react";
import BrandLogo from "../BrandLogo";
import { sidebarMenu } from "./const";

export default function SidebarTag() {
    const pathname = usePathname();
    const { state } = useSidebar();

    const isActive = (path: string) => pathname === path;

    return (
        <Sidebar
            collapsible="icon"
            variant="sidebar"
            className="border-r border-purple-900/30 bg-[#140D24] text-gray-200 backdrop-blur-md shadow-xl w-[16rem]"
        >
            <SidebarContent className="bg-transparent text-gray-200 p-2">
                <SidebarGroup>
                    <SidebarGroupLabel className="transition-none! duration-0! px-3! opacity-100! !mt-2 text-purple-300 font-semibold text-sm uppercase tracking-wide mb-2">
                        <Link href="/home" className="flex items-center">
                            <BrandLogo
                                size={state === "expanded" ? "md" : "sm"}
                                showText={state === "expanded"}
                                variant="white"
                            />
                        </Link>
                    </SidebarGroupLabel>

                    <SidebarGroupContent className="mt-6">
                        <SidebarMenu>
                            {sidebarMenu.map((item) => {
                                const Icon = item.icon;
                                if (item?.children) {
                                    return (
                                        <Collapsible
                                            key={item.title}
                                            defaultOpen
                                            className="group/collapsible"
                                        >
                                            <SidebarMenuItem>
                                                <CollapsibleTrigger asChild>
                                                    <SidebarMenuButton className="text-gray-300 hover:bg-white/10 hover:text-white transition">
                                                        <Icon className="w-4 h-4 text-purple-400" />
                                                        <span>
                                                            {item.title}
                                                        </span>
                                                        <ChevronRight className="ml-auto transition-transform group-data-[state=open]/collapsible:rotate-90 text-gray-400" />
                                                    </SidebarMenuButton>
                                                </CollapsibleTrigger>
                                                <CollapsibleContent>
                                                    <SidebarMenuSub className="border-l border-purple-900/40 ml-4 pl-2 my-1">
                                                        {item.children.map(
                                                            (child) => (
                                                                <SidebarMenuSubItem
                                                                    key={
                                                                        child.title
                                                                    }
                                                                >
                                                                    <SidebarMenuButton
                                                                        asChild
                                                                        className={`px-3 py-2 rounded-md text-sm transition ${
                                                                            isActive(
                                                                                child.href
                                                                            )
                                                                                ? "bg-purple-600/30 text-purple-200 font-medium border border-purple-500/40"
                                                                                : "text-gray-400 hover:bg-white/5 hover:text-white"
                                                                        }`}
                                                                    >
                                                                        <Link
                                                                            href={
                                                                                child.href
                                                                            }
                                                                        >
                                                                            {
                                                                                child.title
                                                                            }
                                                                        </Link>
                                                                    </SidebarMenuButton>
                                                                </SidebarMenuSubItem>
                                                            )
                                                        )}
                                                    </SidebarMenuSub>
                                                </CollapsibleContent>
                                            </SidebarMenuItem>
                                        </Collapsible>
                                    );
                                }

                                return (
                                    <SidebarMenuItem key={item.title}>
                                        <SidebarMenuButton
                                            asChild
                                            className={`flex items-center gap-2 px-3 py-2 rounded-md transition ${
                                                isActive(item?.href || "")
                                                    ? "bg-gradient-to-r from-purple-600 to-indigo-600 text-white font-medium shadow-md shadow-purple-900/40"
                                                    : "text-gray-300 hover:bg-white/10 hover:text-white"
                                            }`}
                                        >
                                            <Link href={item?.href || ""}>
                                                <Icon className="w-4 h-4 text-purple-400" />
                                                <span>{item.title}</span>
                                            </Link>
                                        </SidebarMenuButton>
                                    </SidebarMenuItem>
                                );
                            })}
                        </SidebarMenu>
                    </SidebarGroupContent>
                </SidebarGroup>
            </SidebarContent>
        </Sidebar>
    );
}
