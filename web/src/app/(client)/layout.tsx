"use client";
import AIChat from "@/share/components/ai-chat/AIChat";
import Header from "@/share/layout/Header";

export default function Layout({ children }: { children: React.ReactNode }) {
    return (
        <>
            <Header />
            <main className="pt-[calc(4.1rem+1px)] sm:pt-[calc(4.5rem+1px)]">{children}</main>
            <AIChat />
            {/* <Footer /> */}
        </>
    );
}
