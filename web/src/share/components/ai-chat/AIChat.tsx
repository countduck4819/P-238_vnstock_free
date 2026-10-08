"use client";

import { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { useRouter, usePathname } from "next/navigation";
import { motion, AnimatePresence, useMotionValue, animate, type PanInfo } from "framer-motion";
import {
    Paperclip,
    FileText,
    X,
    Send,
    Sparkles,
    Bot,
    UploadCloud,
    Maximize2,
    Minimize2,
    LogIn,
    RotateCcw,
} from "lucide-react";
import { pushUserMessage, clearMessages } from "@/store/ai-chat/aiChat.reducer";
import { askAIQuery } from "@/store/ai-chat/aiChat.api";
import { useAppDispatch, useAppSelector } from "@/redux/hooks";
import { useAuth } from "@/auth/AuthProvider";
import { cn } from "@/lib/utils";
import { api } from "@/utils/axiosInstance";
import StreamingMessage from "./StreamingMessage";
import "@/css/chat-ai.css";

interface AttachedFile {
    file: File;
    name: string;
    size: string;
}

const POS_STORAGE_KEY = "ai_assist_button_position";
let globalSavedAiPosition: { x: number; y: number; isLeft: boolean } | null = null;

function getSavedPosition() {
    if (globalSavedAiPosition) return globalSavedAiPosition;
    if (typeof window !== "undefined") {
        try {
            const raw = sessionStorage.getItem(POS_STORAGE_KEY);
            if (raw) {
                const parsed = JSON.parse(raw);
                if (typeof parsed?.x === "number" && typeof parsed?.y === "number") {
                    globalSavedAiPosition = parsed;
                    return parsed;
                }
            }
        } catch {
            // Ignore
        }
    }
    return null;
}

export default function AIChat() {
    const [mounted, setMounted] = useState(false);
    const [open, setOpen] = useState(false);
    const [isExpanded, setIsExpanded] = useState(false);
    const [question, setQuestion] = useState("");
    const [attachedFile, setAttachedFile] = useState<AttachedFile | null>(null);
    const [isDragging, setIsDragging] = useState(false);
    const [streamedIndices, setStreamedIndices] = useState<Set<number>>(new Set());

    useEffect(() => {
        setMounted(true);
    }, []);

    const fileInputRef = useRef<HTMLInputElement | null>(null);
    const boxRef = useRef<HTMLDivElement | null>(null);
    const buttonRef = useRef<HTMLDivElement | null>(null);
    const previousLengthRef = useRef(0);
    const isDraggingButtonRef = useRef(false);
    const posX = useMotionValue(0);
    const posY = useMotionValue(0);
    const [isDockedOnLeft, setIsDockedOnLeft] = useState(false);
    const dispatch = useAppDispatch();
    const { user } = useAuth();
    const router = useRouter();
    const pathname = usePathname();

    const { messages, loading } = useAppSelector((s) => s.aiChat);

    // Apple AssistiveTouch initial position & resize adjustment (Preserves saved position across modals)
    useEffect(() => {
        if (!mounted || typeof window === "undefined") return;
        const buttonWidth = 56;
        const buttonHeight = 56;
        const marginX = 20;

        const saved = getSavedPosition();
        let targetX = window.innerWidth - buttonWidth - marginX;
        let targetY = window.innerHeight - buttonHeight - 90;

        if (saved) {
            targetX = saved.isLeft ? marginX : window.innerWidth - buttonWidth - marginX;
            targetY = Math.max(72, Math.min(window.innerHeight - buttonHeight - 80, saved.y));
            setIsDockedOnLeft(saved.isLeft);
        } else {
            setIsDockedOnLeft(false);
        }

        posX.set(targetX);
        posY.set(targetY);
        globalSavedAiPosition = { x: targetX, y: targetY, isLeft: targetX < window.innerWidth / 2 };

        let lastWidth = window.innerWidth;
        const handleResize = () => {
            // Tránh trigger giả khi chỉ mở/đóng modal làm đổi scrollbar (thay đổi dưới 20px)
            if (Math.abs(window.innerWidth - lastWidth) < 20) return;
            lastWidth = window.innerWidth;

            const current = globalSavedAiPosition;
            if (!current) return;

            const newX = current.isLeft ? marginX : window.innerWidth - buttonWidth - marginX;
            const newY = Math.max(
                72,
                Math.min(window.innerHeight - buttonHeight - 80, current.y)
            );
            posX.set(newX);
            posY.set(newY);
            globalSavedAiPosition = { x: newX, y: newY, isLeft: current.isLeft };
        };

        window.addEventListener("resize", handleResize);
        return () => window.removeEventListener("resize", handleResize);
    }, [mounted, posX, posY]);

    // If history is loaded in bulk, mark existing messages as already streamed
    useEffect(() => {
        if (messages.length > previousLengthRef.current + 1) {
            setStreamedIndices(new Set(messages.map((_, idx) => idx)));
        }
        previousLengthRef.current = messages.length;
    }, [messages]);

    // Mỗi khi vào trang hoặc load lại trang: tự động làm mới đoạn chat
    useEffect(() => {
        dispatch(clearMessages());
        setStreamedIndices(new Set());
        setQuestion("");
        setAttachedFile(null);
        if (fileInputRef.current) {
            fileInputRef.current.value = "";
        }
    }, [pathname, dispatch]);

    // Listen for external open chat events
    useEffect(() => {
        const handleOpenAIChat = (e: Event) => {
            const customEvent = e as CustomEvent<{ prompt?: string }>;
            setOpen(true);
            if (customEvent.detail?.prompt) {
                setQuestion(customEvent.detail.prompt);
            }
        };

        window.addEventListener("open-ai-chat", handleOpenAIChat);
        return () => {
            window.removeEventListener("open-ai-chat", handleOpenAIChat);
        };
    }, []);

    // Handle File Selection
    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file) {
            processSelectedFile(file);
        }
    };

    const processSelectedFile = (file: File) => {
        if (file.type !== "application/pdf" && !file.name.endsWith(".pdf")) {
            alert("Vui lòng chỉ chọn tệp định dạng PDF (Báo cáo tài chính).");
            return;
        }

        const sizeInMB = (file.size / (1024 * 1024)).toFixed(2);
        setAttachedFile({
            file,
            name: file.name,
            size: `${sizeInMB} MB`,
        });
    };

    const removeAttachedFile = () => {
        setAttachedFile(null);
        if (fileInputRef.current) {
            fileInputRef.current.value = "";
        }
    };

    // Quick prompt click
    const handleQuickPrompt = (promptText: string) => {
        setQuestion(promptText);
    };



    // Send message logic
    const sendMessage = async () => {
        if (!question.trim() && !attachedFile) return;

        const currentText =
            question.trim() ||
            (attachedFile ? `Phân tích Báo cáo Tài chính: ${attachedFile.name}` : "");

        dispatch(pushUserMessage(currentText));
        dispatch(askAIQuery({ userId: user?.id, question: currentText }));

        setQuestion("");
        setAttachedFile(null);
        if (fileInputRef.current) fileInputRef.current.value = "";
    };

    // Auto scroll to bottom on new messages
    useEffect(() => {
        if (!boxRef.current) return;
        requestAnimationFrame(() => {
            boxRef.current!.scrollTo({
                top: boxRef.current!.scrollHeight,
                behavior: "smooth",
            });
        });
    }, [messages, loading]);

    // Drag and drop handlers
    const handleDragOver = (e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(true);
    };

    const handleDragLeave = (e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(false);
    };

    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(false);
        const file = e.dataTransfer.files?.[0];
        if (file) {
            processSelectedFile(file);
        }
    };

    // Apple AssistiveTouch Magnetic Auto-Docking
    const handleButtonDragEnd = (
        _: MouseEvent | TouchEvent | PointerEvent,
        info: PanInfo
    ) => {
        const dist = Math.hypot(info.offset.x, info.offset.y);
        if (dist > 6) {
            setTimeout(() => {
                isDraggingButtonRef.current = false;
            }, 120);
        } else {
            isDraggingButtonRef.current = false;
        }

        if (typeof window === "undefined") return;

        const buttonWidth = 56;
        const buttonHeight = 56;
        const marginX = 20;
        const topMargin = 72;
        const bottomMargin = 80;

        const rect = buttonRef.current?.getBoundingClientRect();
        const currentLeft = rect ? rect.left : info.point.x - buttonWidth / 2;
        const currentTop = rect ? rect.top : info.point.y - buttonHeight / 2;

        const screenWidth = window.innerWidth;
        const screenHeight = window.innerHeight;

        const isLeft = currentLeft + buttonWidth / 2 < screenWidth / 2;
        setIsDockedOnLeft(isLeft);

        const targetX = isLeft ? marginX : screenWidth - buttonWidth - marginX;
        const targetY = Math.max(
            topMargin,
            Math.min(screenHeight - buttonHeight - bottomMargin, currentTop)
        );

        const saved = { x: targetX, y: targetY, isLeft };
        globalSavedAiPosition = saved;
        try {
            sessionStorage.setItem(POS_STORAGE_KEY, JSON.stringify(saved));
        } catch {
            // Ignore
        }

        animate(posX, targetX, {
            type: "spring",
            stiffness: 450,
            damping: 28,
            mass: 0.7,
        });

        animate(posY, targetY, {
            type: "spring",
            stiffness: 450,
            damping: 28,
            mass: 0.7,
        });
    };

    const chatContent = (
        <>
            {/* Floating Trigger Button (Apple AssistiveTouch Magnetic Auto-Docking) */}
            {!open && (
                <motion.div
                    ref={buttonRef}
                    drag
                    dragMomentum={false}
                    dragElastic={0.15}
                    style={{ x: posX, y: posY }}
                    onDragStart={() => {
                        isDraggingButtonRef.current = true;
                    }}
                    onDragEnd={handleButtonDragEnd}
                    whileHover={{ scale: 1.08 }}
                    whileTap={{ scale: 0.94 }}
                    className="fixed top-0 left-0 z-[99999] ai-chat-trigger pointer-events-auto cursor-grab active:cursor-grabbing touch-none select-none"
                    title="Nhấn để mở chat • Kéo và thả để tự động hít về mép màn hình"
                >
                    <div
                        onClick={(e) => {
                            e.stopPropagation();
                            if (isDraggingButtonRef.current) return;
                            if (!user) {
                                router.push("/login");
                                return;
                            }
                            setOpen(true);
                        }}
                        className="group relative select-none"
                    >
                        <div className="absolute inset-0 bg-gradient-to-r from-cyan-400 via-blue-500 to-indigo-500 rounded-2xl blur-xl opacity-40 group-hover:opacity-80 transition-opacity" />
                        <div className="absolute inset-0 bg-gradient-to-r from-cyan-300 via-blue-400 to-indigo-400 rounded-2xl blur-lg opacity-50 animate-pulse" />

                        <div className="relative w-[3.5rem] h-[3.5rem] bg-gradient-to-br from-cyan-500 via-blue-600 to-indigo-600 rounded-2xl shadow-2xl transition-all duration-200 flex items-center justify-center border border-white/40">
                            <Bot className="w-7 h-7 text-white drop-shadow-md group-hover:rotate-12 transition-transform" />
                            <Sparkles className="w-4 h-4 text-yellow-300 absolute -top-1 -right-1 animate-spin" />
                        </div>

                        {/* Tag AI hỗ trợ (Căn giữa chuẩn xác trên nút bấm, chữ cân đối đẹp mắt) */}
                        <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-2.5 py-0.5 bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 rounded-full text-[11px] font-semibold text-white shadow-md border border-white/30 whitespace-nowrap flex items-center justify-center gap-1.5 pointer-events-none transition-all group-hover:scale-105">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse shrink-0" />
                            <span className="leading-tight tracking-wide">AI hỗ trợ</span>
                        </div>
                    </div>
                </motion.div>
            )}

            {/* Chat Dialog Window */}
            <AnimatePresence>
                {open && (
                    <motion.div
                        initial={{ opacity: 0, y: "1.5rem", scale: 0.95 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        exit={{ opacity: 0, y: "1.5rem", scale: 0.95 }}
                        transition={{ duration: 0.22, ease: "easeOut" }}
                        onDragOver={handleDragOver}
                        onDragLeave={handleDragLeave}
                        onDrop={handleDrop}
                        className={cn(
                            "ai-chat-window fixed z-[99999] flex flex-col overflow-hidden transition-all duration-300 pointer-events-auto",
                            "bg-white/98 dark:bg-slate-900/98 backdrop-blur-2xl rounded-2xl shadow-2xl border border-neutral-200/90 dark:border-slate-800",
                            isExpanded
                                ? "inset-2 sm:inset-10 w-auto h-auto max-w-[55rem] mx-auto"
                                : "inset-x-2 bottom-16 top-16 sm:inset-auto sm:right-[1.5rem] sm:bottom-[5.5rem] md:right-[3rem] md:bottom-[6.5rem] w-auto sm:w-[28rem] xl:w-[35rem] h-auto sm:h-[38rem] max-h-[90vh] sm:max-h-[85vh]",
                            isDragging && "border-2 border-dashed border-indigo-500 bg-indigo-50/50 dark:bg-indigo-950/40"
                        )}
                    >
                        {/* Drag overlay notice */}
                        {isDragging && (
                            <div className="absolute inset-0 z-50 bg-indigo-600/10 backdrop-blur-sm flex flex-col items-center justify-center text-indigo-700 dark:text-indigo-300 pointer-events-none">
                                <UploadCloud className="w-14 h-14 animate-bounce mb-2" />
                                <span className="font-semibold text-lg">Thả tệp PDF Báo cáo Tài chính vào đây</span>
                                <span className="text-sm opacity-80">AI sẽ tự động nạp và phân tích dữ liệu</span>
                            </div>
                        )}

                        {/* Chat Header */}
                        <div className="px-4 py-3 bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 text-white flex items-center justify-between border-b border-indigo-900/50">
                            <div className="flex items-center gap-3">
                                <div className="relative">
                                    <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-cyan-400 to-indigo-500 flex items-center justify-center shadow-md">
                                        <Bot className="w-5 h-5 text-white" />
                                    </div>
                                    <span className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 bg-emerald-400 border-2 border-slate-900 rounded-full" />
                                </div>
                                <div>
                                    <span className="font-semibold text-sm tracking-wide">Trợ lý ảo FinSight</span>
                                    <p className="text-[11px] text-slate-300">
                                        Đọc hiểu BCTC • Phân tích cơ cấu nợ • Đánh giá cổ phiếu
                                    </p>
                                </div>
                            </div>

                            <div className="flex items-center gap-1.5">
                                <button
                                    type="button"
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        setIsExpanded(!isExpanded);
                                    }}
                                    className="p-1.5 text-slate-300 hover:text-white rounded-lg hover:bg-white/10 transition-colors cursor-pointer"
                                    title={isExpanded ? "Thu nhỏ" : "Mở rộng"}
                                >
                                    {isExpanded ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
                                </button>
                                <button
                                    type="button"
                                    onPointerDown={(e) => {
                                        e.stopPropagation();
                                        setOpen(false);
                                    }}
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        setOpen(false);
                                    }}
                                    className="p-1.5 text-slate-300 hover:text-white hover:bg-rose-500/20 rounded-lg transition-colors cursor-pointer"
                                    title="Đóng chat AI"
                                >
                                    <X className="w-5 h-5" />
                                </button>
                            </div>
                        </div>

                        {/* Quick Prompts Bar */}
                        <div className="px-3 py-2 bg-slate-50 dark:bg-slate-950 border-b border-neutral-200/70 dark:border-slate-800 flex items-center gap-1.5 overflow-x-auto no-scrollbar text-xs">
                            <span className="text-slate-400 shrink-0 font-medium pl-1 flex items-center gap-1">
                                <Sparkles className="w-3 h-3 text-amber-500" /> Gợi ý:
                            </span>
                            <button
                                onClick={() => handleQuickPrompt("Phân tích cơ cấu doanh thu & lợi nhuận BCTC")}
                                className="shrink-0 px-2.5 py-1 rounded-full bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 hover:border-indigo-400 hover:bg-indigo-50 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300 hover:text-indigo-700 dark:hover:text-white transition-all shadow-2xs cursor-pointer"
                            >
                                📊 Phân tích BCTC
                            </button>
                            <button
                                onClick={() => handleQuickPrompt("Đánh giá tỷ lệ nợ vay & khả năng thanh toán")}
                                className="shrink-0 px-2.5 py-1 rounded-full bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 hover:border-indigo-400 hover:bg-indigo-50 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300 hover:text-indigo-700 dark:hover:text-white transition-all shadow-2xs cursor-pointer"
                            >
                                ⚖️ Đánh giá nợ & rủi ro
                            </button>
                            <button
                                onClick={() => handleQuickPrompt("Nhận định điểm mua và vùng hỗ trợ cổ phiếu")}
                                className="shrink-0 px-2.5 py-1 rounded-full bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 hover:border-indigo-400 hover:bg-indigo-50 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300 hover:text-indigo-700 dark:hover:text-white transition-all shadow-2xs cursor-pointer"
                            >
                                📈 Điểm mua kỹ thuật
                            </button>
                        </div>

                        {/* Messages Box */}
                        <div
                            ref={boxRef}
                            className="flex-1 overflow-y-auto p-4 space-y-4 bg-gradient-to-b from-slate-50/50 via-white to-slate-50/30 dark:from-slate-950 dark:via-slate-900 dark:to-slate-950"
                        >
                            {messages.length === 0 && (
                                <div className="flex items-start gap-2.5 max-w-[95%] sm:max-w-[90%]">
                                    <div className="w-7 h-7 rounded-lg bg-indigo-100 dark:bg-indigo-900/60 border border-indigo-200 dark:border-indigo-700 flex items-center justify-center shrink-0 mt-0.5 text-indigo-700 dark:text-indigo-300">
                                        <Bot className="w-4 h-4" />
                                    </div>
                                    <div className="bg-white dark:bg-slate-800/90 border border-slate-200/80 dark:border-slate-700/80 p-3.5 rounded-2xl rounded-tl-xs text-sm text-slate-800 dark:text-slate-100 shadow-2xs leading-relaxed ai-answer">
                                        Xin chào <b>{user?.fullName || user?.username || "Nhà đầu tư"}</b>!<br/><br/>
                                        Tôi là <b>Trợ lý ảo FinSight</b>. Tôi có thể hỗ trợ bạn bóc tách số liệu Báo cáo Tài chính (PDF), định giá và phân tích chuyên sâu cổ phiếu.<br/><br/>
                                        <i>👉 Hãy gửi câu hỏi hoặc nhấn nút <b>&quot;Tải BCTC (PDF)&quot;</b> để bắt đầu nhé!</i>
                                    </div>
                                </div>
                            )}

                            {messages.map((msg: { sender: string; text: string }, i: number) =>
                                msg.sender === "user" ? (
                                    <div key={i} className="flex flex-col items-end">
                                        <div className="bg-gradient-to-r from-blue-600 to-indigo-600 text-white px-4 py-2.5 rounded-2xl rounded-tr-xs max-w-[85%] text-sm shadow-md leading-relaxed">
                                            {msg.text}
                                        </div>
                                    </div>
                                ) : (
                                    <div key={i} className="flex items-start gap-2.5 max-w-[95%] sm:max-w-[90%]">
                                        <div className="w-7 h-7 rounded-lg bg-indigo-100 dark:bg-indigo-900/60 border border-indigo-200 dark:border-indigo-700 flex items-center justify-center shrink-0 mt-0.5 text-indigo-700 dark:text-indigo-300">
                                            <Bot className="w-4 h-4" />
                                        </div>
                                        <div
                                            className={cn(
                                                "bg-white dark:bg-slate-800/90 border border-slate-200/80 dark:border-slate-700/80 p-3.5 rounded-2xl rounded-tl-xs text-sm text-slate-800 dark:text-slate-100 shadow-2xs leading-relaxed",
                                                "ai-answer"
                                            )}
                                        >
                                            <StreamingMessage
                                                content={msg.text}
                                                shouldStream={i === messages.length - 1 && !streamedIndices.has(i)}
                                                onStreamUpdate={() => {
                                                    if (boxRef.current) {
                                                        boxRef.current.scrollTop = boxRef.current.scrollHeight;
                                                    }
                                                }}
                                                onStreamComplete={() => {
                                                    setStreamedIndices((prev) => new Set(prev).add(i));
                                                }}
                                            />
                                        </div>
                                    </div>
                                )
                            )}

                            {/* Loading state */}
                            {loading && (
                                <div className="flex items-start gap-2.5 max-w-[85%]">
                                    <div className="w-7 h-7 rounded-lg bg-indigo-100 dark:bg-indigo-900/60 border border-indigo-200 dark:border-indigo-700 flex items-center justify-center shrink-0 text-indigo-700 dark:text-indigo-300">
                                        <Bot className="w-4 h-4" />
                                    </div>
                                    <div className="bg-white dark:bg-slate-800 border border-slate-200/80 dark:border-slate-700 px-4 py-3 rounded-2xl rounded-tl-xs shadow-2xs flex items-center gap-2">
                                        <span className="w-2 h-2 rounded-full bg-indigo-600 dark:bg-indigo-400 animate-bounce" />
                                        <span
                                            className="w-2 h-2 rounded-full bg-indigo-600 dark:bg-indigo-400 animate-bounce"
                                            style={{ animationDelay: "0.2s" }}
                                        />
                                        <span
                                            className="w-2 h-2 rounded-full bg-indigo-600 dark:bg-indigo-400 animate-bounce"
                                            style={{ animationDelay: "0.4s" }}
                                        />
                                        <span className="text-xs text-slate-500 dark:text-slate-400 font-medium ml-1">
                                            AI đang phân tích dữ liệu...
                                        </span>
                                    </div>
                                </div>
                            )}
                        </div>

                        {/* Selected File Banner Preview */}
                        {attachedFile && (
                            <div className="px-3 py-2 bg-gradient-to-r from-red-50 via-amber-50 to-red-50 dark:from-red-950/40 dark:via-amber-950/30 dark:to-red-950/40 border-t border-red-200/80 dark:border-red-900/60 flex items-center justify-between">
                                <div className="flex items-center gap-2.5 min-w-0">
                                    <div className="w-8 h-8 rounded-lg bg-red-100 dark:bg-red-900/60 border border-red-300 dark:border-red-700 flex items-center justify-center text-red-600 dark:text-red-300 shrink-0">
                                        <FileText className="w-4 h-4" />
                                    </div>
                                    <div className="min-w-0">
                                        <div className="flex items-center gap-1.5">
                                            <span className="text-xs font-semibold text-slate-800 dark:text-slate-200 truncate max-w-[14rem] sm:max-w-[20rem]">
                                                {attachedFile.name}
                                            </span>
                                            <span className="text-[10px] text-red-600 dark:text-red-400 font-medium bg-red-100 dark:bg-red-900/50 px-1 rounded">
                                                PDF
                                            </span>
                                        </div>
                                        <span className="text-[11px] text-slate-500 dark:text-slate-400">
                                            {attachedFile.size} • Sẵn sàng phân tích
                                        </span>
                                    </div>
                                </div>

                                <button
                                    onClick={removeAttachedFile}
                                    className="p-1 text-slate-400 hover:text-red-600 rounded-md hover:bg-red-100/50 dark:hover:bg-red-900/50 transition-colors cursor-pointer"
                                    title="Hủy file đính kèm"
                                >
                                    <X className="w-4 h-4" />
                                </button>
                            </div>
                        )}

                        {/* Input & Action Bar */}
                        <div className="p-3 bg-white dark:bg-slate-900 border-t border-neutral-200 dark:border-slate-800 flex flex-col gap-2">
                            {/* Hidden File Input */}
                            <input
                                ref={fileInputRef}
                                type="file"
                                accept=".pdf,application/pdf"
                                className="hidden"
                                onChange={handleFileChange}
                            />

                            <div className="flex items-center gap-2">
                                {/* Button Tải lên BCTC (PDF) */}
                                <button
                                    type="button"
                                    onClick={() => fileInputRef.current?.click()}
                                    className={cn(
                                        "h-10 px-3 rounded-xl border flex items-center gap-1.5 text-xs font-medium transition-all shadow-2xs shrink-0 cursor-pointer",
                                        attachedFile
                                            ? "bg-red-50 dark:bg-red-950/40 border-red-300 dark:border-red-800 text-red-700 dark:text-red-300"
                                            : "bg-slate-50 dark:bg-slate-800 border-slate-200 dark:border-slate-700 hover:border-indigo-400 hover:bg-indigo-50 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 hover:text-indigo-700 dark:hover:text-white"
                                    )}
                                    title="Tải lên Báo cáo tài chính định dạng PDF"
                                >
                                    <Paperclip className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
                                    <span className="hidden sm:inline">
                                        {attachedFile ? "Đã đính kèm PDF" : "Tải BCTC (PDF)"}
                                    </span>
                                </button>

                                {/* Input Text */}
                                <div className="relative flex-1">
                                    <input
                                        value={question}
                                        onChange={(e) => setQuestion(e.target.value)}
                                        onKeyDown={(e) => e.key === "Enter" && sendMessage()}
                                        className="w-full h-10 border border-slate-200 dark:border-slate-700 rounded-xl px-3 text-sm focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 dark:focus:ring-indigo-900/50 bg-slate-50/50 dark:bg-slate-800/80 text-slate-900 dark:text-white transition-all placeholder:text-slate-400 dark:placeholder:text-slate-500"
                                        placeholder={
                                            attachedFile
                                                ? "Hỏi về BCTC này (hoặc nhấn Gửi để phân tích tổng quan)..."
                                                : "Hỏi AI về mã CP, BCTC hoặc ngành..."
                                        }
                                    />
                                </div>

                                {/* Send Button */}
                                <button
                                    type="button"
                                    onClick={sendMessage}
                                    disabled={!question.trim() && !attachedFile}
                                    className={cn(
                                        "h-10 px-4 rounded-xl flex items-center justify-center gap-1.5 text-sm font-medium text-white transition-all shadow-md shrink-0 cursor-pointer",
                                        !question.trim() && !attachedFile
                                            ? "bg-slate-300 dark:bg-slate-700 cursor-not-allowed shadow-none"
                                            : "bg-gradient-to-r from-blue-600 via-indigo-600 to-indigo-700 hover:from-blue-700 hover:to-indigo-800 active:scale-95"
                                    )}
                                >
                                    <Send className="w-4 h-4" />
                                    <span className="hidden sm:inline">Gửi</span>
                                </button>
                            </div>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </>
    );

    if (!mounted) return null;
    return createPortal(chatContent, document.body);
}
