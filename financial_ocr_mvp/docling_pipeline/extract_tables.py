"""Extract physical table grids from a DoclingDocument JSON export.

This module deliberately does not OCR, normalize values, repair spelling, or infer
accounting semantics. It only places Docling cells at their reported row/column
offsets and carries source coordinates alongside the resulting grid.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _text(cell: dict[str, Any]) -> str | None:
    value = cell.get("text")
    return None if value is None else str(value)


def _page_number(table: dict[str, Any]) -> int | None:
    provenance = table.get("prov") or []
    if not provenance:
        return None
    return provenance[0].get("page_no")


def _bbox(table: dict[str, Any]) -> dict[str, Any] | None:
    provenance = table.get("prov") or []
    return provenance[0].get("bbox") if provenance else None


def table_to_grid(table: dict[str, Any], table_id: int, source_pdf: str) -> dict[str, Any]:
    """Convert one Docling table to a position-preserving raw grid."""
    cells = table.get("data", {}).get("table_cells", [])
    if not cells:
        return {
            "table_id": table_id,
            "headers": [],
            "rows": [],
            "source": {"pdf": source_pdf, "page": _page_number(table), "table": table_id},
            "cell_sources": [],
            "status": "needs_review",
            "errors": ["table has no table_cells"],
        }

    max_row = max(cell.get("end_row_offset_idx", 0) for cell in cells)
    max_col = max(cell.get("end_col_offset_idx", 0) for cell in cells)
    grid: list[list[str | None]] = [[None] * max_col for _ in range(max_row)]
    sources: list[list[dict[str, Any] | None]] = [[None] * max_col for _ in range(max_row)]

    for cell in cells:
        start_row = cell.get("start_row_offset_idx", 0)
        end_row = cell.get("end_row_offset_idx", start_row + 1)
        start_col = cell.get("start_col_offset_idx", 0)
        end_col = cell.get("end_col_offset_idx", start_col + 1)
        value = _text(cell)

        # For merged cells, preserve the value at the physical top-left position
        # and leave the covered positions empty. Never duplicate the value.
        grid[start_row][start_col] = value
        for row in range(start_row, end_row):
            for col in range(start_col, end_col):
                sources[row][col] = {
                    "pdf": source_pdf,
                    "page": _page_number(table),
                    "table": table_id,
                    "row": row,
                    "column": col,
                    "value": value,
                    "bbox": cell.get("bbox"),
                    "row_span": cell.get("row_span", 1),
                    "col_span": cell.get("col_span", 1),
                }

    header_rows = sorted(
        {
            cell.get("start_row_offset_idx", 0)
            for cell in cells
            if cell.get("column_header") is True
        }
    )
    first_data_row = (max(header_rows) + 1) if header_rows else 0
    errors = []
    if not header_rows:
        errors.append("Docling did not mark any column-header cells")

    return {
        "table_id": table_id,
        "headers": grid[:first_data_row] if header_rows else [],
        "rows": grid[first_data_row:],
        "source": {
            "pdf": source_pdf,
            "page": _page_number(table),
            "table": table_id,
            "bbox": _bbox(table),
        },
        "cell_sources": sources,
        "status": "ok" if not errors else "needs_review",
        "errors": errors,
    }


def extract_tables(docling_data: dict[str, Any]) -> dict[str, Any]:
    """Extract every physical table from a DoclingDocument export."""
    source_pdf = docling_data.get("origin", {}).get("filename", "")
    tables = docling_data.get("tables", [])
    extracted = [table_to_grid(table, index, source_pdf) for index, table in enumerate(tables)]
    return {
        "schema": "financial_raw_grid_v1",
        "source": {"pdf": source_pdf, "method": "Docling physical table extraction"},
        "tables": extracted,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract raw grids from Docling JSON")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    with args.input.open(encoding="utf-8") as file:
        docling_data = json.load(file)
    result = extract_tables(docling_data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
    print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()
