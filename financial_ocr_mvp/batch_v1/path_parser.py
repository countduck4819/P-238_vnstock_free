"""Parse the actual MinIO financial-report object layout.

Accepted layout:
  financial-reports/consolidated/{ticker}/{year}/quarterly/*.pdf
  financial-reports/consolidated/{ticker}/{year}/annual/*.pdf

The complete object path is returned unchanged as ``source_path``.
"""
from __future__ import annotations

import re
from typing import Any

YEAR_RE = re.compile(r"^\d{4}$")
QUARTER_RE = re.compile(r"(?:^|[_-])Q([1-4])(?:[_-]|\.|$)", re.IGNORECASE)
PDF_RE = re.compile(r"\.pdf$", re.IGNORECASE)


def parse_source_path(source_path: str) -> dict[str, Any] | None:
    original = source_path.strip("/")
    parts = original.split("/")
    if len(parts) < 5 or not PDF_RE.search(parts[-1]):
        return None

    year_index = next((i for i, part in enumerate(parts) if YEAR_RE.fullmatch(part)), None)
    if year_index is None or year_index == 0 or year_index + 1 >= len(parts) - 1:
        return None

    period_dir = parts[year_index + 1].lower()
    if period_dir not in {"quarterly", "annual"}:
        return None

    ticker = parts[year_index - 1].upper()
    year = int(parts[year_index])
    filename = parts[-1]
    quarter_match = QUARTER_RE.search(filename)
    quarter = int(quarter_match.group(1)) if quarter_match else None

    if period_dir == "quarterly" and quarter is None:
        return None
    if period_dir == "annual" and quarter is not None:
        return None

    return {
        "ticker": ticker,
        "year": year,
        "quarter": quarter,
        "report_type": "quarterly" if period_dir == "quarterly" else "annual",
        "source_path": original,
    }
