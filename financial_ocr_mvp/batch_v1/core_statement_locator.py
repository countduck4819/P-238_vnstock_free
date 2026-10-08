"""Early-stop locator for the three primary financial statements."""
from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
from pathlib import Path
from typing import Any

import fitz

from .page_selector import image_features, normalize, ocr_heading, similarity
from .section_taxonomy import SECTION_TAXONOMY


CORE_ALIASES = {
    "balance_sheet": SECTION_TAXONOMY["balance_sheet"]["aliases"],
    "income_statement": (
        "bao cao ket qua hoat dong kinh doanh",
        "bao cao ket qua kinh doanh",
        "ket qua hoat dong kinh doanh",
        "income statement",
        "statement of profit or loss",
    ),
    "cash_flow": SECTION_TAXONOMY["cash_flow"]["aliases"],
}

TEXT_GATE = {"min_coverage_ratio": 0.30, "min_meaningful_pages": 2, "min_page_chars": 40, "min_page_tokens": 8}
FINANCIAL_TERMS = ("bang can doi", "tinh hinh tai chinh", "tai san", "no phai tra", "von chu so huu", "ket qua kinh doanh", "doanh thu", "gia von", "loi nhuan", "luu chuyen tien", "hoat dong kinh doanh", "hoat dong dau tu", "hoat dong tai chinh")

def _normalized(text: str) -> str:
    value = unicodedata.normalize("NFKD", text.casefold())
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value)).strip()

def _meaningful_text(text: str) -> bool:
    value = _normalized(text)
    if len(value.split()) < TEXT_GATE["min_page_tokens"] or len(value) < TEXT_GATE["min_page_chars"]:
        return False
    metadata = ("digitally signed", "foxit reader", "certificate", "signature metadata")
    return not (any(x in value for x in metadata) and not any(x in value for x in FINANCIAL_TERMS))

def text_quality(native: list[str]) -> dict[str, Any]:
    meaningful = [i + 1 for i, text in enumerate(native) if _meaningful_text(text)]
    keyword_pages = [i + 1 for i, text in enumerate(native) if any(x in _normalized(text) for x in FINANCIAL_TERMS)]
    coverage = len(meaningful) / max(len(native), 1)
    return {"total_pages": len(native), "pages_with_text": sum(bool(t.strip()) for t in native), "pages_with_meaningful_text": meaningful, "text_coverage_ratio": round(coverage, 4), "whole_document_text_length": sum(map(len, native)), "financial_keyword_pages": keyword_pages, "text_layer_usable": coverage >= TEXT_GATE["min_coverage_ratio"] and len(meaningful) >= TEXT_GATE["min_meaningful_pages"]}

def _verified_matches(text: str, matches: list[dict[str, Any]], table_signal: bool) -> list[dict[str, Any]]:
    value = _normalized(text)
    evidence = {"balance_sheet": "tai san" in value and ("no phai tra" in value or "von chu so huu" in value), "income_statement": "doanh thu" in value and ("gia von" in value or "loi nhuan" in value), "cash_flow": "luu chuyen tien" in value and "hoat dong" in value}
    return [m for m in matches if table_signal and evidence.get(m["concept"], False)]


def locate_in_text(text: str) -> list[dict[str, Any]]:
    matches = []
    for concept, aliases in CORE_ALIASES.items():
        score = max((similarity(text, alias) for alias in aliases), default=0.0)
        if score >= 0.58:
            matches.append({
                "concept": concept,
                "score": round(score, 3),
                "original_heading": text[:300],
            })
    return sorted(matches, key=lambda item: item["score"], reverse=True)


def locate(
    pdf_path: Path,
    stage1_pages: int = 20,
    stage2_pages: int = 30,
    max_search_pages: int = 40,
    ocr_dpi: int = 48,
) -> dict[str, Any]:
    started = time.perf_counter()
    with fitz.open(pdf_path) as document:
        total_pages = len(document)
        native = [page.get_text("text") for page in document]
        quality = text_quality(native)
        use_ocr = not quality["text_layer_usable"]
        ocr = None
        if use_ocr or any(not _meaningful_text(text) for text in native):
            from rapidocr_onnxruntime import RapidOCR
            ocr = RapidOCR()

        upper_bound = min(total_pages, max_search_pages)
        scan_ranges = [(1, min(stage1_pages, upper_bound))]
        if upper_bound > stage1_pages:
            scan_ranges.append((stage1_pages + 1, min(stage2_pages, upper_bound)))
        next_start = stage2_pages + 1
        while next_start <= upper_bound:
            scan_ranges.append((next_start, min(next_start + 9, upper_bound)))
            next_start += 10

        evidence: dict[int, dict[str, Any]] = {}
        found: dict[str, dict[str, Any]] = {}
        searched_pages = 0
        early_stop = False
        for range_start, range_end in scan_ranges:
            if len(found) == 3:
                early_stop = True
                break
            for page_number in range(range_start, range_end + 1):
                page = document[page_number - 1]
                text = native[page_number - 1]
                source = "pdf_text_layer"
                if not _meaningful_text(text):
                    text = ocr_heading(page, ocr_dpi, ocr)
                    source = f"rapidocr_heading_{ocr_dpi}dpi"
                features = image_features(page)
                matches = locate_in_text(normalize(text))
                verified = _verified_matches(text, matches, bool(features["table_signal"]))
                evidence[page_number] = {
                    "page": page_number,
                    "text_source": source,
                    "original_heading": text[:300],
                    "matches": matches,
                    "verified_matches": verified,
                    "table_signal": features["table_signal"],
                    "number_count": len(text.split()),
                }
                searched_pages += 1
                for match in verified:
                    current = found.get(match["concept"])
                    if current is None or match["score"] > current["confidence"]:
                        found[match["concept"]] = {
                            "start_page": page_number,
                            "confidence": match["score"],
                            "original_heading": match["original_heading"],
                        }
                if len(found) == 3:
                    early_stop = page_number < total_pages
                    break
            if len(found) == 3:
                break

        selected: set[int] = set()
        sections: dict[str, dict[str, Any]] = {}
        for concept, item in found.items():
            start = int(item["start_page"])
            end = min(total_pages, start + 1)
            # Keep one likely continuation page; never cross a detected new
            # core statement heading.
            later_starts = [
                int(other["start_page"])
                for other_concept, other in found.items()
                if other_concept != concept and int(other["start_page"]) > start
            ]
            if later_starts:
                end = min(end, min(later_starts) - 1)
            pages = list(range(start, max(start, end) + 1))
            selected.update(pages)
            sections[concept] = {
                "pages": pages,
                "confidence": item["confidence"],
                "original_heading": item["original_heading"],
            }

        missing = sorted(set(CORE_ALIASES) - set(found))
        result = {
            "schema": "core_statement_locator_v1",
            "policy": "early_stop_heading_only_conservative",
            "pdf": str(pdf_path),
            "total_pages": total_pages,
            "searched_pages": searched_pages,
            "early_stop": early_stop,
            "search_ranges": [[start, end] for start, end in scan_ranges],
            "max_search_pages": max_search_pages,
            "selector_mode": "heading_ocr" if use_ocr else "pdf_text_layer",
            "routing_mode": "scanned" if use_ocr else "native_or_hybrid",
            "text_quality": quality,
            "ocr_pages": [p for p, item in evidence.items() if item["text_source"].startswith("rapidocr")],
            "native_text_pages": [p for p, item in evidence.items() if item["text_source"] == "pdf_text_layer"],
            "sections": sections,
            "selected_pages": sorted(selected),
            "missing_sections": missing,
            "navigation_status": "OK" if not missing else "needs_review",
            "locator_seconds": round(time.perf_counter() - started, 3),
            "page_evidence": list(evidence.values()),
        }
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Locate core financial statements with early stop")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-search-pages", type=int, default=40)
    parser.add_argument("--ocr-dpi", type=int, default=48)
    args = parser.parse_args()
    result = locate(args.pdf, max_search_pages=args.max_search_pages, ocr_dpi=args.ocr_dpi)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: result[key] for key in (
        "total_pages", "searched_pages", "early_stop", "sections",
        "selected_pages", "missing_sections", "navigation_status", "locator_seconds",
    )}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
