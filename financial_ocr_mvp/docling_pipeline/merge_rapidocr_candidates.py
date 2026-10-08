"""Merge RapidOCR v1 and v2 cell-review candidates without changing source data."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

CONFIDENCE_SCORE = {"low": 0, "medium": 1, "high": 2}


def key(item: dict[str, Any]) -> tuple[str, str, str, str]:
    return tuple(str(item.get(field, "")) for field in ("page", "table", "row", "column"))


def confidence(item: dict[str, Any]) -> int:
    label = str(item.get("confidence", "")).lower()
    if label in CONFIDENCE_SCORE:
        return CONFIDENCE_SCORE[label]
    return 0


def candidate_value(item: dict[str, Any], version: str) -> str:
    if version == "v2":
        return str(item.get("best_candidate") or item.get("second_candidate") or "")
    return str(item.get("ocr_value") or "")


def is_candidate(item: dict[str, Any], version: str) -> bool:
    value = candidate_value(item, version)
    return item.get("decision") == "candidate" and bool(value)


def choose(items: list[tuple[str, dict[str, Any]]]) -> tuple[str, dict[str, Any]] | None:
    candidates = [(version, item) for version, item in items if is_candidate(item, version)]
    if not candidates:
        return None
    # Higher confidence wins. On a tie, v2 wins because it is the newer retry.
    return max(candidates, key=lambda pair: (confidence(pair[1]), pair[0] == "v2"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge RapidOCR v1/v2 reviews")
    parser.add_argument("v1_review", type=Path)
    parser.add_argument("v2_review", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    v1 = json.loads(args.v1_review.read_text(encoding="utf-8"))
    v2 = json.loads(args.v2_review.read_text(encoding="utf-8"))
    v1_items = v1.get("items", [])
    v2_items = v2.get("items", [])

    grouped: dict[tuple[str, str, str, str], list[tuple[str, dict[str, Any]]]] = {}
    for item in v1_items:
        grouped.setdefault(key(item), []).append(("v1", item))
    for item in v2_items:
        grouped.setdefault(key(item), []).append(("v2", item))

    merged: list[dict[str, Any]] = []
    for cell_key, sources in sorted(grouped.items()):
        selected = choose(sources)
        base = next(item for _, item in sources)
        selected_version = selected[0] if selected else None
        selected_item = selected[1] if selected else None
        selected_value = candidate_value(selected_item, selected_version) if selected_item else ""
        selected_decision = "candidate" if selected else "pending_review"

        record = {
            "page": base.get("page"),
            "table": base.get("table"),
            "row": base.get("row"),
            "column": base.get("column"),
            "old_value": base.get("old_value"),
            "ocr_value": selected_value,
            "selected_candidate": selected_value,
            "confidence": selected_item.get("confidence", "low") if selected_item else "low",
            "decision": selected_decision,
            "method": "RapidOCR_v2" if selected_version == "v2" else "RapidOCR",
            "selected_source": selected_version,
            "bbox": base.get("bbox"),
            "source_reviews": {
                "v1": next((item for version, item in sources if version == "v1"), None),
                "v2": next((item for version, item in sources if version == "v2"), None),
            },
        }
        merged.append(record)

    result = {
        "schema": "merged_rapidocr_candidates_v1",
        "policy": "candidate_only_no_source_overwrite",
        "summary": {
            "total_cells": len(merged),
            "candidates": sum(item["decision"] == "candidate" for item in merged),
            "needs_review": sum(item["decision"] == "pending_review" for item in merged),
            "selected_from_v1": sum(item["selected_source"] == "v1" for item in merged),
            "selected_from_v2": sum(item["selected_source"] == "v2" for item in merged),
            "raw_values_overwritten": 0,
        },
        "items": merged,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Saved:", args.output)
    print(result["summary"])


if __name__ == "__main__":
    main()
