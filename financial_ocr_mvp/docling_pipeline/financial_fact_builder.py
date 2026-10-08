"""Build confidence-based financial facts without overwriting source evidence."""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

NUMBER = re.compile(r"^\(?[0-9]{1,3}(?:\.[0-9]{3})*\)?$")


def normalize_number(value: Any) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"[0-9.()\s]+", text):
        return re.sub(r"\s+", "", text)
    return text


def valid_number(value: Any) -> bool:
    return bool(NUMBER.fullmatch(normalize_number(value)))


def normalize_label(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text.replace("đ", "d")).strip()


def table_source(table: dict[str, Any]) -> dict[str, Any]:
    return table.get("source_grid", table)


def table_key(table: dict[str, Any]) -> str:
    source = table_source(table)
    return str(table.get("table_id", source.get("table_id", "")))


def cell_key(item: dict[str, Any]) -> tuple[str, str, str, str]:
    return tuple(str(item.get(field, "")) for field in ("page", "table", "row", "column"))


def header_path(headers: list[list[Any]], column: int) -> list[str]:
    path: list[str] = []
    for header_row in headers:
        value = header_row[column] if column < len(header_row) else None
        if value not in (None, ""):
            path.append(str(value))
        elif path:
            path.append(path[-1])
    return path


def period_from_path(path: list[str], source: dict[str, Any]) -> str:
    if source.get("period"):
        return str(source["period"])
    return path[0] if path else ""


def confidence_for_candidate(item: dict[str, Any]) -> float:
    score = item.get("source_reviews", {}).get("v1", {})
    score = score.get("ocr_score")
    if score is None:
        score = item.get("source_reviews", {}).get("v2", {}) or {}
        score = score.get("ocr_score")
    if score is not None:
        return round(float(score), 6)
    return {"high": 0.92, "medium": 0.75, "low": 0.50}.get(
        str(item.get("confidence", "low")).lower(), 0.50
    )


def confidence_for_raw() -> float:
    # Docling OCR is usable evidence, but it has not passed cell verification.
    return 0.70


def main() -> None:
    parser = argparse.ArgumentParser(description="Build confidence-based financial facts")
    parser.add_argument("semantic_mapping", type=Path)
    parser.add_argument("merged_candidates", type=Path)
    parser.add_argument("validation_report", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    mapping_document = json.loads(args.semantic_mapping.read_text(encoding="utf-8"))
    merged_document = json.loads(args.merged_candidates.read_text(encoding="utf-8"))
    validation_document = json.loads(args.validation_report.read_text(encoding="utf-8"))
    mapping = mapping_document.get("mapping", mapping_document)
    candidate_items = {cell_key(item): item for item in merged_document.get("items", [])}
    validation_items = {cell_key(item): item for item in validation_document.get("items", [])}
    candidate_by_location = {(str(item.get("table", "")), str(item.get("row", "")), str(item.get("column", ""))): item for item in merged_document.get("items", [])}
    validation_by_location = {(str(item.get("table", "")), str(item.get("row", "")), str(item.get("column", ""))): item for item in validation_document.get("items", [])}

    facts: list[dict[str, Any]] = []
    review_queue: list[dict[str, Any]] = []

    for table in mapping.get("tables", []):
        source = table_source(table)
        headers = source.get("headers", [])
        rows = source.get("rows", [])
        source_info = source.get("source", {})
        page = source_info.get("page", table.get("page"))
        table_id = table_key(table)

        for row_index, row in enumerate(rows):
            if len(row) < 2:
                continue
            row_name = row[1] or ""
            row_code = row[2] or ""
            for column, raw_value in enumerate(row):
                if column < 4:
                    continue
                key = (str(page), str(table_id), str(row_index), str(column))
                location_key = (str(table_id), str(row_index), str(column))
                candidate_item = candidate_items.get(key) or candidate_by_location.get(location_key)
                validation_item = validation_items.get(key) or validation_by_location.get(location_key, {})
                candidate_value = ""
                if candidate_item and candidate_item.get("decision") == "candidate":
                    candidate_value = candidate_item.get("selected_candidate") or candidate_item.get("ocr_value") or ""
                candidate_valid = valid_number(candidate_value)
                raw_valid = valid_number(raw_value)
                candidate_verified = bool(validation_item.get("approved_candidate"))

                fact_page = candidate_item.get("page", page) if candidate_item else page
                if candidate_valid:
                    final_value = candidate_value
                    status = "verified" if candidate_verified else "candidate"
                    verification_status = "verified" if candidate_verified else "candidate"
                    confidence = confidence_for_candidate(candidate_item)
                    method = candidate_item.get("method", "RapidOCR")
                    reason = "financial_validation_approved" if candidate_verified else "high_quality_ocr_candidate"
                elif raw_valid:
                    final_value = raw_value
                    status = "candidate"
                    verification_status = "candidate"
                    confidence = confidence_for_raw()
                    method = "Docling"
                    reason = "raw_numeric_value_without_verified_retry"
                elif raw_value not in (None, "") or candidate_value:
                    final_value = ""
                    status = "needs_review"
                    verification_status = "needs_review"
                    confidence = 0.0
                    method = candidate_item.get("method", "Docling") if candidate_item else "Docling"
                    reason = "raw_and_candidate_numeric_values_unusable"
                else:
                    continue

                path = header_path(headers, column)
                fact = {
                    "metric": str(row_name),
                    "code": str(row_code),
                    "period": period_from_path(path, source),
                    "value": final_value,
                    "raw_value": raw_value,
                    "candidate_value": candidate_value,
                    "final_value": final_value,
                    "confidence": confidence,
                    "status": status,
                    "verification_status": verification_status,
                    "reason": reason,
                    "column": {
                        "index": column,
                        "header_path": path,
                        "label": path[-1] if path else "",
                    },
                    "source": {
                        "pdf": source_info.get("pdf", ""),
                        "page": fact_page,
                        "table": table_id,
                        "row": row_index,
                        "column": column,
                        "bbox": (
                            candidate_item.get("bbox") if candidate_item else
                            (source.get("cell_sources", [[None]])[row_index][column].get("bbox")
                             if row_index < len(source.get("cell_sources", []))
                             and column < len(source.get("cell_sources", [])[row_index])
                             and source.get("cell_sources", [])[row_index][column] else None)
                        ),
                        "method": method,
                    },
                }
                facts.append(fact)
                if status == "needs_review":
                    review_queue.append(fact)

    summary = {
        "total_facts": len(facts),
        "verified": sum(f["status"] == "verified" for f in facts),
        "candidates": sum(f["status"] == "candidate" for f in facts),
        "needs_review": sum(f["status"] == "needs_review" for f in facts),
        "raw_values_overwritten": 0,
    }
    result = {
        "schema": "financial_fact_v1",
        "status": "needs_review" if review_queue else "ready",
        "summary": summary,
        "facts": facts,
        "review_queue": review_queue,
        "provenance": {
            "semantic_mapping": str(args.semantic_mapping),
            "merged_candidates": str(args.merged_candidates),
            "validation_report": str(args.validation_report),
        },
        "policy": {
            "raw_value_overwrite": False,
            "candidate_delete": False,
            "accounting_inference": False,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Saved:", args.output)
    print(summary)


if __name__ == "__main__":
    main()
