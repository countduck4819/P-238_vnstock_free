"""Promote only financially validated OCR candidates.

Raw values and the original mapping are preserved. Verification metadata is
attached separately at table level so the physical grid remains unchanged.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path
from typing import Any

NUMBER = re.compile(r"^\(?[0-9]{1,3}(?:\.[0-9]{3})*\)?$")


def cell_key(item: dict[str, Any]) -> tuple[str, str, str, str]:
    return tuple(str(item.get(field, "")) for field in ("page", "table", "row", "column"))


def valid_number(value: Any) -> bool:
    text = str(value or "").strip()
    if re.fullmatch(r"[0-9.()\s]+", text):
        text = re.sub(r"\s+", "", text)
    return bool(NUMBER.fullmatch(text))


def table_key(table: dict[str, Any]) -> str:
    source = table.get("source_grid", {})
    return str(table.get("table_id", source.get("table_id", "")))


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote financially validated OCR candidates")
    parser.add_argument("mapping", type=Path)
    parser.add_argument("merged_candidates", type=Path)
    parser.add_argument("validation_report", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    mapping_document = json.loads(args.mapping.read_text(encoding="utf-8"))
    merged_document = json.loads(args.merged_candidates.read_text(encoding="utf-8"))
    validation_document = json.loads(args.validation_report.read_text(encoding="utf-8"))

    merged_items = {cell_key(item): item for item in merged_document.get("items", [])}
    validation_items = {cell_key(item): item for item in validation_document.get("items", [])}
    promoted = 0
    pending = 0
    verifications: list[dict[str, Any]] = []

    for key, candidate_item in merged_items.items():
        # Promotion evaluates candidate cells only; cells without a selected
        # candidate remain in the upstream review file.
        candidate = candidate_item.get("selected_candidate") or candidate_item.get("ocr_value") or ""
        if candidate_item.get("decision") != "candidate" or not candidate:
            continue
        validation = validation_items.get(key, {})
        confidence = str(candidate_item.get("confidence", "")).lower()
        finance_approved = bool(validation.get("approved_candidate"))
        context_approved = validation.get("period_context", {}).get("status") == "corroborated"
        relevant_finance_failed = validation.get("candidate_relevant_finance_status") == "fail"
        eligible = bool(
            candidate_item.get("decision") == "candidate"
            and confidence == "high"
            and valid_number(candidate)
            and not relevant_finance_failed
            and (finance_approved or context_approved)
        )

        if eligible:
            promoted += 1
            verification = {
                "status": "verified",
                "method": candidate_item.get("method", "RapidOCR"),
                "confidence": candidate_item.get("confidence"),
                "reason": "high_confidence_valid_numeric_candidate_passed_financial_validation",
            }
            verified_value = candidate
        else:
            pending += 1
            verification = {
                "status": "pending_review",
                "method": candidate_item.get("method", "RapidOCR"),
                "confidence": candidate_item.get("confidence"),
                "reason": (
                    validation.get("reason")
                    or ("candidate_not_corroborrated_by_period_context" if not context_approved else "candidate_not_approved_by_financial_validation")
                ),
            }
            verified_value = ""

        record = {
            "page": candidate_item.get("page"),
            "table": candidate_item.get("table"),
            "row": candidate_item.get("row"),
            "column": candidate_item.get("column"),
            "raw_value": candidate_item.get("old_value"),
            "candidate_value": candidate,
            "verified_value": verified_value,
            "verification": verification,
            "bbox": candidate_item.get("bbox"),
            "expanded_bbox": (
                (candidate_item.get("source_reviews", {}).get("v2") or {})
                .get("expanded_bbox")
            ),
            "selected_source": candidate_item.get("selected_source"),
        }
        verifications.append(record)

    output_mapping = copy.deepcopy(mapping_document)
    mapping = output_mapping.get("mapping", output_mapping)
    tables = mapping.get("tables", []) if isinstance(mapping, dict) else []
    by_table: dict[str, list[dict[str, Any]]] = {}
    for record in verifications:
        by_table.setdefault(str(record.get("table", "")), []).append(record)
    for table in tables:
        table["cell_verifications"] = by_table.get(table_key(table), [])

    result = {
        "schema": "final_verified_semantic_mapping_v1",
        "status": "verified" if pending == 0 else "partial",
        "summary": {
            "total_candidates": len(verifications),
            "verified_values": promoted,
            "pending_review": pending,
            "raw_values_overwritten": 0,
        },
        "mapping": mapping,
        "cell_verifications": verifications,
        "policy": {
            "raw_value_overwrite": False,
            "candidate_delete": False,
            "canonical_output": False,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Saved:", args.output)
    print(result["summary"])


if __name__ == "__main__":
    main()
