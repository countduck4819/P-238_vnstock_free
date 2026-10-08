export default function BadgeTag({
    label,
    color,
}: {
    label: string;
    color: string;
}) {
    return (
        <span className={`px-2 py-1 rounded-md text-xs font-medium ${color}`}>
            {label}
        </span>
    );
}
