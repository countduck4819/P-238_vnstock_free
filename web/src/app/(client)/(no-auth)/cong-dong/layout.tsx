"use client";

import { CommunityRealtimeProvider } from "./components/CommunityRealtimeProvider";

export default function CommunityLayout({ children }: { children: React.ReactNode }) {
    return <CommunityRealtimeProvider>{children}</CommunityRealtimeProvider>;
}
