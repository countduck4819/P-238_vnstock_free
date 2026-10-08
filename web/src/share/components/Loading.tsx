"use client";
import "@/css/loading.css";
function Loading() {
    return (
        <div className="fixed z-[99999] inset-0 flex flex-col items-center justify-center min-h-screen overflow-hidden bg-gradient-to-b from-[#F5F3FF] via-[#EDE9FE] to-[#E0E7FF] text-gray-800">
            <div className="loader">
                <li className="ball"></li>
                <li className="ball"></li>
                <li className="ball"></li>
            </div>
        </div>
    );
}

export default Loading;
