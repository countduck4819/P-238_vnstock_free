"""Create a selected-pages PDF and preserve original page traceability."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import fitz

from .page_selector import select_pages


def create_filtered_pdf(pdf_path: Path, output_dir: Path, ocr_dpi: int = 48, use_ocr: bool = False) -> dict[str, Any]:
    selection = select_pages(pdf_path, ocr_dpi, use_ocr)
    selected = selection["selected_pages"]
    output_dir.mkdir(parents=True, exist_ok=True)
    selected_pdf = output_dir / "selected_pages.pdf"
    filtered = fitz.open()
    with fitz.open(pdf_path) as source:
        for page_number in selected:
            filtered.insert_pdf(source, from_page=page_number - 1, to_page=page_number - 1)
    filtered.save(selected_pdf)
    filtered.close()
    page_map = {str(index + 1): page for index, page in enumerate(selected)}
    selection["page_map"] = page_map
    selection["selected_pdf"] = str(selected_pdf)
    (output_dir / "page_selection.json").write_text(json.dumps(selection, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "page_map.json").write_text(json.dumps(page_map, ensure_ascii=False, indent=2), encoding="utf-8")
    return selection


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a selected-pages working PDF")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--ocr-dpi", type=int, default=48)
    parser.add_argument("--ocr-heading", action="store_true")
    args = parser.parse_args()
    result = create_filtered_pdf(args.pdf, args.output_dir, args.ocr_dpi, args.ocr_heading)
    print(json.dumps({key: result[key] for key in ("selected_pdf", "original_pages", "selected_pages", "skipped_pages", "uncertain_pages", "core_pages", "missing_core_sections", "navigation_status", "reduction_percent", "page_map")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
