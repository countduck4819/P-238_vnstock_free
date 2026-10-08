"use client";
type ImportantStatus = "TARGET_HIT" | "STOP_LOSS";

const statusLabelMap: Record<ImportantStatus, string> = {
    TARGET_HIT: "Chốt lời",
    STOP_LOSS: "Cắt lỗ",
};

const statusColorMap: Record<ImportantStatus, string> = {
    TARGET_HIT: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20",
    STOP_LOSS: "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20",
};

interface StatusBadgeProps {
    status?: ImportantStatus;
}

export const BadgeStatus: React.FC<StatusBadgeProps> = ({ status }) => {
    if (!status) return null;
    const label = statusLabelMap[status];
    const color = statusColorMap[status];

    return (
        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold border ${color}`}>
            {label}
        </span>
    );
};
