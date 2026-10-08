import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import SidebarTag from "@/share/components/admin/SidebarTag";
import "./index.css";
export default function Layout({ children }: { children: React.ReactNode }) {
    return (
        <SidebarProvider>
            <div className="min-h-screen flex w-full bg-gradient-to-r from-[#120C1F] to-[#1A1034] text-white">
                <SidebarTag />
                <main className="flex-1 flex flex-col min-w-0 overflow-x-hidden">
                    <header className="flex items-center gap-3 px-6 py-3 border-b border-purple-900/30 bg-black/20 backdrop-blur-sm sticky top-0 z-10">
                        <SidebarTrigger className="text-gray-300 hover:text-white hover:bg-purple-900/40 p-2 rounded-lg transition" />
                        <span className="text-xs font-semibold uppercase tracking-wider text-purple-300/80">FinSight Admin Portal</span>
                    </header>
                    <div className="flex-1 w-full">
                        {children}
                    </div>
                </main>
            </div>
        </SidebarProvider>
    );
}
