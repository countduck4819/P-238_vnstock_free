from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .normalization_rules import NUMBER, PAGE_MARKER, VERSION, normalize_text


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def tag_counts(text: str) -> dict[str, int]:
    return {tag: len(re.findall(fr"<{tag}\b", text, re.I)) for tag in ("table", "tr", "td", "th")}


def numeric_tokens(text: str) -> list[str]:
    return NUMBER.findall(text)


def normalize_file(raw_path: Path, output_path: Path, metadata: dict[str, object]) -> dict[str, object]:
    raw_bytes = raw_path.read_bytes()
    raw = raw_bytes.decode("utf-8", errors="replace")
    normalized, changes, warnings = normalize_text(raw)
    before_pages = [int(x) for x in PAGE_MARKER.findall(raw)]
    after_pages = [int(x) for x in PAGE_MARKER.findall(normalized)]
    before_numbers, after_numbers = numeric_tokens(raw), numeric_tokens(normalized)
    before_html, after_html = tag_counts(raw), tag_counts(normalized)
    if before_pages != after_pages: warnings.append("page_markers_changed")
    if before_html != after_html: warnings.append("html_tag_counts_changed")
    if sorted(before_numbers) != sorted(after_numbers): warnings.append("numeric_tokens_changed")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(normalized, encoding="utf-8", newline="")
    out_bytes = normalized.encode("utf-8")
    return {**metadata, "raw_bytes": len(raw_bytes), "normalized_bytes": len(out_bytes), "raw_sha256": digest(raw_bytes), "normalized_sha256": digest(out_bytes), "page_count_before": len(before_pages), "page_count_after": len(after_pages), "page_markers_before": before_pages, "page_markers_after": after_pages, "html_counts_before": before_html, "html_counts_after": after_html, "numeric_tokens_before": len(before_numbers), "numeric_tokens_after": len(after_numbers), "numeric_tokens_removed": len(before_numbers) - len(after_numbers), "numeric_tokens_added": len(after_numbers) - len(before_numbers), "changes": changes, "warnings": warnings, "normalization_status": "warning" if warnings else "success", "normalizer_version": VERSION}
