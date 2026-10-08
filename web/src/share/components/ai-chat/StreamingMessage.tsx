"use client";

import React, { useEffect, useState, useRef, useMemo } from "react";
import { cn } from "@/lib/utils";

interface HtmlToken {
    type: "tag" | "text";
    content: string;
    tagName?: string;
    isClosing?: boolean;
    isSelfClosing?: boolean;
}

function tokenizeHtml(html: string): HtmlToken[] {
    if (!html) return [];
    const tokens: HtmlToken[] = [];
    const regex = /(<\/?[a-zA-Z][a-zA-Z0-9]*(?:\s+[^>]*?)?\/?>)|([^<]+)/g;
    let match;

    while ((match = regex.exec(html)) !== null) {
        if (match[1]) {
            const tagStr = match[1];
            const isClosing = tagStr.startsWith("</");
            const isSelfClosing =
                tagStr.endsWith("/>") ||
                /<br\s*\/?>|<hr\s*\/?>|<img[^>]*>/i.test(tagStr);
            const tagNameMatch = tagStr.match(/<\/?([a-zA-Z0-9]+)/);
            const tagName = tagNameMatch ? tagNameMatch[1].toLowerCase() : "";

            tokens.push({
                type: "tag",
                content: tagStr,
                tagName,
                isClosing,
                isSelfClosing,
            });
        } else if (match[2]) {
            tokens.push({
                type: "text",
                content: match[2],
            });
        }
    }

    return tokens;
}

function getTotalTextLength(tokens: HtmlToken[]): number {
    return tokens.reduce(
        (sum, token) =>
            token.type === "text" ? sum + token.content.length : sum,
        0
    );
}

function buildPartialHtml(tokens: HtmlToken[], charCount: number): string {
    let currentChars = 0;
    let result = "";
    const openTagsStack: string[] = [];

    for (const token of tokens) {
        if (currentChars >= charCount) {
            break;
        }

        if (token.type === "tag") {
            if (token.isClosing) {
                if (
                    openTagsStack.length > 0 &&
                    openTagsStack[openTagsStack.length - 1] === token.tagName
                ) {
                    openTagsStack.pop();
                    result += token.content;
                }
            } else {
                result += token.content;
                if (!token.isSelfClosing && token.tagName) {
                    openTagsStack.push(token.tagName);
                }
            }
        } else if (token.type === "text") {
            const needed = charCount - currentChars;
            if (token.content.length <= needed) {
                result += token.content;
                currentChars += token.content.length;
            } else {
                result += token.content.slice(0, needed);
                currentChars += needed;
                break;
            }
        }
    }

    // Close any unclosed tags in reverse order
    for (let i = openTagsStack.length - 1; i >= 0; i--) {
        result += `</${openTagsStack[i]}>`;
    }

    return result;
}

interface StreamingMessageProps {
    content: string;
    shouldStream?: boolean;
    onStreamUpdate?: () => void;
    onStreamComplete?: () => void;
    className?: string;
}

export default function StreamingMessage({
    content,
    shouldStream = true,
    onStreamUpdate,
    onStreamComplete,
    className,
}: StreamingMessageProps) {
    const tokens = useMemo(() => tokenizeHtml(content), [content]);
    const totalLength = useMemo(() => getTotalTextLength(tokens), [tokens]);

    const [visibleChars, setVisibleChars] = useState<number>(() =>
        shouldStream ? 0 : totalLength
    );
    const [isStreaming, setIsStreaming] = useState<boolean>(() =>
        shouldStream && totalLength > 0
    );

    const onUpdateRef = useRef(onStreamUpdate);
    const onCompleteRef = useRef(onStreamComplete);

    useEffect(() => {
        onUpdateRef.current = onStreamUpdate;
        onCompleteRef.current = onStreamComplete;
    });

    useEffect(() => {
        if (!shouldStream || totalLength === 0) {
            setVisibleChars(totalLength);
            setIsStreaming(false);
            return;
        }

        setVisibleChars(0);
        setIsStreaming(true);

        let current = 0;
        // Dynamic step to ensure natural pacing
        // Short text: 1-2 chars per tick; Long text: 3-8 chars per tick
        const step = Math.max(1, Math.min(8, Math.ceil(totalLength / 100)));
        const intervalMs = 18;

        const timer = setInterval(() => {
            current += step;
            if (current >= totalLength) {
                current = totalLength;
                setVisibleChars(totalLength);
                setIsStreaming(false);
                clearInterval(timer);
                if (onCompleteRef.current) {
                    onCompleteRef.current();
                }
            } else {
                setVisibleChars(current);
            }

            if (onUpdateRef.current) {
                onUpdateRef.current();
            }
        }, intervalMs);

        return () => clearInterval(timer);
    }, [content, shouldStream, totalLength]);

    const displayedHtml = useMemo(() => {
        if (!isStreaming || visibleChars >= totalLength) {
            return content;
        }
        return buildPartialHtml(tokens, visibleChars);
    }, [content, tokens, isStreaming, visibleChars, totalLength]);

    const handleSkip = () => {
        if (isStreaming) {
            setVisibleChars(totalLength);
            setIsStreaming(false);
            if (onCompleteRef.current) {
                onCompleteRef.current();
            }
            if (onUpdateRef.current) {
                onUpdateRef.current();
            }
        }
    };

    return (
        <div
            onClick={handleSkip}
            className={cn("relative leading-relaxed transition-opacity cursor-default", className)}
        >
            <div
                dangerouslySetInnerHTML={{ __html: displayedHtml }}
                className="inline"
            />
            {isStreaming && (
                <span
                    className="inline-block w-2 h-4 ml-1 bg-gradient-to-r from-blue-500 to-indigo-600 dark:from-cyan-400 dark:to-indigo-400 rounded-xs animate-pulse align-middle shadow-xs"
                    title="Đang trả lời (Nhấn để hiện toàn bộ)"
                />
            )}
        </div>
    );
}
