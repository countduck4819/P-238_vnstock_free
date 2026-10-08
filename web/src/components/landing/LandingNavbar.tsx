"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import Image from "next/image";
import { motion, AnimatePresence } from "framer-motion";
import { Sparkles, ArrowRight, Menu, X } from "lucide-react";

import BrandLogo from "@/share/components/BrandLogo";

export default function LandingNavbar() {
    const [scrolled, setScrolled] = useState(false);
    const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
    const [activeSection, setActiveSection] = useState<string>("");

    const navItems = [
        { label: "Tính năng", href: "#capabilities" },
        { label: "Cách hoạt động", href: "#how-it-works" },
        { label: "AI & RAG", href: "#ai-rag" },
        { label: "Minh bạch (Explainable)", href: "#explainability" },
        { label: "Sản phẩm", href: "#product-showcase" },
    ];

    // Silky smooth scroll function with cubic easing
    const smoothScrollTo = useCallback((targetY: number, duration = 650) => {
        const startY = window.scrollY;
        const difference = targetY - startY;
        if (Math.abs(difference) < 5) return;

        const startTime = performance.now();
        const easeInOutCubic = (t: number) =>
            t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;

        const step = (currentTime: number) => {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);
            const ease = easeInOutCubic(progress);

            window.scrollTo(0, startY + difference * ease);

            if (progress < 1) {
                requestAnimationFrame(step);
            }
        };

        requestAnimationFrame(step);
    }, []);

    // Scroll spy to detect active section in viewport
    useEffect(() => {
        const handleScroll = () => {
            setScrolled(window.scrollY > 20);

            const sectionIds = [
                "capabilities",
                "how-it-works",
                "ai-rag",
                "explainability",
                "product-showcase",
            ];

            const triggerPoint = Math.min(window.innerHeight * 0.35, 260);
            let current = "";

            for (const id of sectionIds) {
                const el = document.getElementById(id);
                if (el) {
                    const rect = el.getBoundingClientRect();
                    // When the top has reached the trigger threshold and bottom is still visible
                    if (rect.top <= triggerPoint && rect.bottom > 80) {
                        current = `#${id}`;
                    }
                }
            }

            // If user scrolled to the bottom of the page, activate the last section
            if (
                !current &&
                window.innerHeight + window.scrollY >=
                document.documentElement.scrollHeight - 100
            ) {
                current = `#${sectionIds[sectionIds.length - 1]}`;
            }

            setActiveSection(current);
        };

        window.addEventListener("scroll", handleScroll, { passive: true });
        handleScroll();
        return () => window.removeEventListener("scroll", handleScroll);
    }, []);

    const handleNavClick = (
        e: React.MouseEvent<HTMLAnchorElement>,
        href: string
    ) => {
        if (href.startsWith("#")) {
            e.preventDefault();
            const targetId = href.substring(1);
            const targetElement = document.getElementById(targetId);

            if (targetElement) {
                const navHeight = 68; // fixed navbar offset height
                const elementPosition = targetElement.getBoundingClientRect().top;
                const offsetPosition = Math.max(
                    0,
                    elementPosition + window.scrollY - navHeight
                );

                smoothScrollTo(offsetPosition, 650);
                setActiveSection(href);

                if (window.history.pushState) {
                    window.history.pushState(null, "", href);
                }
            }
            setMobileMenuOpen(false);
        }
    };

    return (
        <header
            className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${scrolled
                    ? "bg-slate-950/95 backdrop-blur-md shadow-lg shadow-black/40 border-b border-slate-800"
                    : "bg-slate-950/90 backdrop-blur-md border-b border-slate-850"
                }`}
        >
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
                {/* Brand Logo */}
                <div className="flex items-center gap-3">
                    <Link href="/" className="flex items-center gap-2.5 group">
                        <BrandLogo size="md" variant="white" />
                    </Link>
                </div>

                {/* Desktop Navigation Links with Animated Underline */}
                <nav className="hidden md:flex items-center gap-7 text-sm">
                    {navItems.map((item) => {
                        const isActive = activeSection === item.href;
                        return (
                            <a
                                key={item.label}
                                href={item.href}
                                onClick={(e) => handleNavClick(e, item.href)}
                                className={`relative py-2 transition-colors duration-200 group ${isActive
                                        ? "text-white font-semibold"
                                        : "text-slate-300 hover:text-white font-medium"
                                    }`}
                            >
                                <span>{item.label}</span>

                                {/* Gliding Active Underline using Framer Motion */}
                                {isActive ? (
                                    <motion.span
                                        layoutId="navbarActiveUnderline"
                                        className="absolute bottom-0 left-0 right-0 h-[2.5px] rounded-full bg-gradient-to-r from-blue-400 via-indigo-400 to-purple-400 shadow-[0_0_10px_rgba(96,165,250,0.85)]"
                                        transition={{
                                            type: "spring",
                                            stiffness: 380,
                                            damping: 30,
                                        }}
                                    />
                                ) : (
                                    /* Hover Underline for inactive tabs */
                                    <span className="absolute bottom-0 left-0 w-0 h-[2px] rounded-full bg-blue-400/60 transition-all duration-200 group-hover:w-full" />
                                )}
                            </a>
                        );
                    })}
                </nav>

                {/* Desktop CTA Action Button */}
                <div className="hidden sm:flex items-center gap-3">
                    <Link
                        href="/home"
                        className="px-4 py-2 text-sm font-medium text-white bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 hover:from-blue-700 hover:via-indigo-700 hover:to-purple-700 rounded-lg shadow-sm hover:shadow-md hover:shadow-blue-500/20 transition-all flex items-center gap-1.5 group"
                    >
                        <span>Trải nghiệm FinSight</span>
                        <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
                    </Link>
                </div>

                {/* Mobile Hamburger Button */}
                <button
                    onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                    className="md:hidden p-2 text-slate-300 hover:text-white rounded-lg hover:bg-slate-800 focus:outline-none transition-colors"
                    aria-label="Toggle menu"
                >
                    {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
                </button>
            </div>

            {/* Mobile Dropdown Menu */}
            <AnimatePresence>
                {mobileMenuOpen && (
                    <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: "auto" }}
                        exit={{ opacity: 0, height: 0 }}
                        transition={{ duration: 0.2 }}
                        className="md:hidden bg-slate-950 border-b border-slate-800 px-4 pt-3 pb-6 space-y-3 shadow-xl overflow-hidden"
                    >
                        <div className="flex flex-col space-y-1.5">
                            {navItems.map((item) => {
                                const isActive = activeSection === item.href;
                                return (
                                    <a
                                        key={item.label}
                                        href={item.href}
                                        onClick={(e) => handleNavClick(e, item.href)}
                                        className={`px-3.5 py-2.5 text-sm rounded-lg transition-all flex items-center justify-between ${isActive
                                                ? "bg-blue-950/70 text-blue-300 border-l-4 border-blue-500 font-semibold pl-4"
                                                : "text-slate-300 hover:text-white hover:bg-slate-900 font-medium"
                                            }`}
                                    >
                                        <span>{item.label}</span>
                                        {isActive && (
                                            <span className="w-2 h-2 rounded-full bg-blue-400 shadow-[0_0_8px_#60a5fa]" />
                                        )}
                                    </a>
                                );
                            })}
                        </div>
                        <div className="pt-3 border-t border-slate-800 flex flex-col gap-2.5">
                            <Link
                                href="/home"
                                onClick={() => setMobileMenuOpen(false)}
                                className="w-full text-center py-2.5 text-sm font-medium text-white bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 rounded-lg flex items-center justify-center gap-1.5"
                            >
                                <span>Trải nghiệm FinSight</span>
                                <ArrowRight className="w-4 h-4" />
                            </Link>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </header>
    );
}
