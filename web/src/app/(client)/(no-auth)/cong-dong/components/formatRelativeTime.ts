/** "Vừa xong", "5 phút trước", ... then a plain date after a week. */
export function formatRelativeTime(dateStr?: string | null) {
    if (!dateStr) return "Vừa xong";
    const date = new Date(dateStr);
    if (isNaN(date.getTime())) return dateStr;

    const minutes = Math.floor((Date.now() - date.getTime()) / 60000);
    if (minutes < 1) return "Vừa xong";
    if (minutes < 60) return `${minutes} phút trước`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours} giờ trước`;
    const days = Math.floor(hours / 24);
    if (days < 7) return `${days} ngày trước`;
    return `${date.getDate()}/${date.getMonth() + 1}/${date.getFullYear()}`;
}
