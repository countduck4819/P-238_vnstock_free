from __future__ import annotations

import re
import unicodedata

VERSION = "txt_norm_v1"
PAGE_MARKER = re.compile(r"^\s*=+\s*PAGE\s+(\d+)\s*=+\s*$", re.I | re.M)
NUMBER = re.compile(r"(?<![\w])\(?[-+]?\d[\d.,%]*\)?(?![\w])")


def normalize_text(raw: str) -> tuple[str, list[str], list[str]]:
    changes: list[str] = []
    warnings: list[str] = []
    value = raw
    if value.startswith("\ufeff"):
        value = value.lstrip("\ufeff")
        changes.append("bom_removed")
    normalized = unicodedata.normalize("NFC", value)
    if normalized != value:
        changes.append("unicode_normalized")
    value = normalized.replace("\r\n", "\n").replace("\r", "\n")
    if value != normalized:
        changes.append("line_endings_normalized")
    cleaned = "".join(c for c in value if c in "\n\t" or c.isprintable())
    if cleaned != value:
        changes.append("control_chars_removed")
    lines = [line.rstrip() for line in cleaned.split("\n")]
    if "\n".join(lines) != cleaned:
        changes.append("trailing_whitespace_stripped")
    value = "\n".join(lines)
    if not value.endswith("\n"):
        value += "\n"
    return value, changes, warnings
