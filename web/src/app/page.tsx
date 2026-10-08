import { Metadata } from "next";
import LandingThemeEnforcer from "@/components/landing/LandingThemeEnforcer";
import LandingNavbar from "@/components/landing/LandingNavbar";
import LandingHero from "@/components/landing/LandingHero";
import LandingTrustStrip from "@/components/landing/LandingTrustStrip";
import LandingProblem from "@/components/landing/LandingProblem";
import LandingSolution from "@/components/landing/LandingSolution";
import LandingCapabilities from "@/components/landing/LandingCapabilities";
import LandingHowItWorks from "@/components/landing/LandingHowItWorks";
import LandingAIRAG from "@/components/landing/LandingAIRAG";
import LandingExplainability from "@/components/landing/LandingExplainability";
import LandingProductShowcase from "@/components/landing/LandingProductShowcase";
import LandingDifferentiation from "@/components/landing/LandingDifferentiation";
import LandingFinalCTA from "@/components/landing/LandingFinalCTA";
import LandingFooter from "@/components/landing/LandingFooter";

export const metadata: Metadata = {
    title: "FinSight — Nền tảng Phân tích Chứng khoán & Trợ lý AI",
    description:
        "Phân tích cổ phiếu toàn diện kết hợp tín hiệu thị trường, chỉ báo kỹ thuật, báo cáo tài chính và Trợ lý AI giải thích minh bạch.",
};

export default function RootPage() {
    return (
        <div className="min-h-screen bg-white text-slate-900 selection:bg-blue-500 selection:text-white font-sans antialiased overflow-x-hidden">
            {/* Force Light Theme on Landing */}
            <LandingThemeEnforcer />

            {/* 1. Navbar */}
            <LandingNavbar />

            <main>
                {/* 2. Hero Section */}
                <LandingHero />

                {/* 3. Trust & Credibility Strip */}
                <LandingTrustStrip />

                {/* 4. Problem Section */}
                <LandingProblem />

                {/* 5. Solution Section & Pipeline */}
                <LandingSolution />

                {/* 6. Core Capabilities (2x2 Grid) */}
                <LandingCapabilities />

                {/* 7. How It Works (5-Step Scientific Process) */}
                <LandingHowItWorks />

                {/* 8. AI + RAG Grounded Architecture */}
                <LandingAIRAG />

                {/* 9. Explainability & Evidence Proof */}
                <LandingExplainability />

                {/* 10. Product Showcase & Deep-Dive Mockup */}
                <LandingProductShowcase />

                {/* 11. Differentiation Matrix */}
                <LandingDifferentiation />

                {/* 12. Final High-Conversion CTA */}
                <LandingFinalCTA />
            </main>

            {/* 13. Footer + Financial Disclaimer */}
            <LandingFooter />
        </div>
    );
}
