"""Conservative page/section navigator for native and scanned financial PDFs."""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import fitz
from PIL import Image
import numpy as np


def normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", text.casefold())
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def tokens(text: str) -> set[str]:
    return set(normalize(text).split())


def similarity(text: str, alias: str) -> float:
    haystack = normalize(text)
    needle = normalize(alias)
    if not needle:
        return 0.0
    if needle in haystack:
        return 1.0
    overlap = len(tokens(haystack) & tokens(needle)) / max(len(tokens(needle)), 1)
    return max(overlap, SequenceMatcher(None, haystack, needle).ratio() * 0.85)


def image_features(page: fitz.Page) -> dict[str, float | bool]:
    """Cheap vectorized layout signal; it does not OCR or extract values."""
    pixmap = page.get_pixmap(dpi=36, alpha=False)
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples).convert("L")
    width, height = image.size
    sample = image.resize((min(width, 700), min(height, 900)))
    pixels = np.asarray(sample)
    dark = pixels < 220
    strict_dark = pixels < 180
    ink_ratio = float(dark.mean())
    horizontal_dark = (strict_dark.mean(axis=1) >= 0.55).sum()
    vertical_dark = (strict_dark.mean(axis=0) >= 0.55).sum()
    line_signal = (horizontal_dark / max(sample.height, 1)) + (vertical_dark / max(sample.width, 1))
    return {
        "ink_ratio": round(ink_ratio, 5),
        "line_signal": round(float(line_signal), 5),
        "table_signal": bool(line_signal >= 0.006 or ink_ratio >= 0.055),
    }


def ocr_heading(page: fitz.Page, dpi: int, ocr: Any) -> str:
    """OCR only the upper band, not the full financial table."""
    rect = page.rect
    clip = fitz.Rect(rect.x0, rect.y0, rect.x1, rect.y0 + rect.height * 0.38)
    pixmap = page.get_pixmap(dpi=dpi, alpha=False, clip=clip)
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    detected, _ = ocr(image)
    return " ".join(str(item[1]) for item in (detected or []))


def page_evidence(page_number: int, page: fitz.Page, ocr_dpi: int, ocr: Any, use_ocr: bool) -> dict[str, Any]:
    native_text = page.get_text("text")
    features = image_features(page)
    text = native_text
    source = "pdf_text_layer"
    if not text.strip() and use_ocr:
        text = ocr_heading(page, ocr_dpi, ocr)
        source = f"rapidocr_heading_{ocr_dpi}dpi"
    normalized = normalize(text)
    return {
        "page": page_number,
        "text": text,
        "text_source": source,
        "normalized_text": normalized,
        **features,
        "number_count": len(re.findall(r"(?<![a-z])\d[\d.,()%-]{2,}", text)),
    }


def classify(evidence: dict[str, Any], previous: dict[str, Any] | None, following: dict[str, Any] | None) -> dict[str, Any]:
    from .section_taxonomy import SECTION_TAXONOMY, SKIP_ALIASES

    text = evidence["normalized_text"]
    matches: list[dict[str, Any]] = []
    for concept, config in SECTION_TAXONOMY.items():
        best = max((similarity(text, alias) for alias in config["aliases"]), default=0.0)
        if best >= 0.48:
            matches.append({"concept": concept, "kind": config["kind"], "score": round(best, 3)})
    matches.sort(key=lambda item: item["score"], reverse=True)
    skip_score = max((similarity(text, alias) for alias in SKIP_ALIASES), default=0.0)
    neighbor_financial = any(
        item and (item.get("matches") or item.get("table_signal") or item.get("number_count", 0) >= 8)
        for item in (previous, following)
    )
    top = matches[0] if matches else None
    core = top and top["kind"] == "CORE" and top["score"] >= 0.62
    important = top and top["kind"] == "IMPORTANT" and top["score"] >= 0.58
    continuation = bool(
        not top and evidence["table_signal"] and evidence["number_count"] >= 3
        and previous and (previous.get("active_section") or previous.get("classification") in {"KEEP", "UNCERTAIN"})
    )
    if core:
        state, reason = "KEEP", "core_section_match"
    elif important:
        state, reason = "KEEP", "important_section_match"
    elif continuation:
        state, reason = "KEEP", "possible_section_continuation"
    elif skip_score >= 0.78 and not evidence["table_signal"] and evidence["number_count"] < 8:
        state, reason = "SKIP", "clear_text_only_skip_section"
    elif evidence["table_signal"] or evidence["number_count"] >= 3 or neighbor_financial:
        state, reason = "UNCERTAIN", "financial_or_table_signal_without_confident_match"
    else:
        state, reason = "UNCERTAIN", "ambiguous_conservative_keep"
    active = top["concept"] if top else (previous.get("active_section") if continuation and previous else None)
    return {
        "page": evidence["page"],
        "classification": state,
        "reason": reason,
        "active_section": active,
        "matches": matches[:3],
        "skip_score": round(skip_score, 3),
        "table_signal": evidence["table_signal"],
        "ink_ratio": evidence["ink_ratio"],
        "line_signal": evidence["line_signal"],
        "number_count": evidence["number_count"],
        "text_source": evidence["text_source"],
        "original_heading": evidence["text"][:300],
    }


def select_pages(pdf_path: Path, ocr_dpi: int = 48, use_ocr: bool = False) -> dict[str, Any]:
    from rapidocr_onnxruntime import RapidOCR

    with fitz.open(pdf_path) as document:
        native_texts = [page.get_text("text") for page in document]
        ocr = RapidOCR() if use_ocr and not any(text.strip() for text in native_texts) else None
        evidences = []
        for index, page in enumerate(document):
            evidences.append(page_evidence(index + 1, page, ocr_dpi, ocr, use_ocr))
    classified: list[dict[str, Any]] = []
    for index, evidence in enumerate(evidences):
        previous = classified[-1] if classified else None
        following = evidences[index + 1] if index + 1 < len(evidences) else None
        classified.append(classify(evidence, previous, following))
    selected = [item["page"] for item in classified if item["classification"] != "SKIP"]
    core_concepts = {"balance_sheet", "income_statement", "cash_flow"}
    found_core = {match["concept"] for item in classified for match in item["matches"] if match["concept"] in core_concepts}
    missing_core = sorted(core_concepts - found_core)
    sections: list[dict[str, Any]] = []
    for item in classified:
        for match in item["matches"][:1]:
            key = match["concept"]
            existing = next((section for section in sections if section["concept"] == key), None)
            if existing is None:
                sections.append({"concept": key, "original_heading": item["original_heading"], "pages": [item["page"]], "confidence": match["score"]})
            elif item["page"] == existing["pages"][-1] + 1:
                existing["pages"].append(item["page"])
    return {
        "schema": "page_selection_v2",
        "policy": "fuzzy_config_driven_conservative_keep",
        "pdf": str(pdf_path),
        "selector_ocr_dpi": ocr_dpi if use_ocr else None,
        "selector_mode": "heading_ocr" if use_ocr else "image_heuristic_native_text",
        "original_pages": len(classified),
        "selected_pages": selected,
        "skipped_pages": [item["page"] for item in classified if item["classification"] == "SKIP"],
        "uncertain_pages": [item["page"] for item in classified if item["classification"] == "UNCERTAIN"],
        "core_pages": [item["page"] for item in classified if any(m["kind"] == "CORE" for m in item["matches"])],
        "missing_core_sections": missing_core,
        "navigation_status": "needs_review" if missing_core else "OK",
        "reduction_percent": round((1 - len(selected) / len(classified)) * 100, 2) if classified else 0.0,
        "sections": sections,
        "pages": classified,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Conservative financial page selector")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ocr-dpi", type=int, default=48)
    parser.add_argument("--ocr-heading", action="store_true")
    args = parser.parse_args()
    result = select_pages(args.pdf, args.ocr_dpi, args.ocr_heading)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("original_pages", "selected_pages", "skipped_pages", "uncertain_pages", "core_pages", "missing_core_sections", "navigation_status", "reduction_percent")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
