"""Canonicalize validated semantic mappings without changing raw values."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def canonicalize_table(table: dict[str, Any]) -> dict[str, Any]:
    if table.get("status") != "ok":
        raise ValueError("semantic mapping is not approved: needs_review")
    return {
        "document": table["document"],
        "statement": table["statement"],
        "rows": table.get("rows", []),
        "provenance": {
            "raw_value_policy": "preserved_exactly",
            "source_grid_status": table.get("status"),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    data = json.loads(args.input.read_text(encoding="utf-8"))
    tables = data.get("tables", [])
    review = [
        {"table_id": table.get("table_id"), "status": table.get("status"), "errors": table.get("errors", [])}
        for table in tables
        if table.get("status") != "ok"
    ]
    if review:
        review_path = args.output.with_name(args.output.stem + "_needs_review.json")
        review_path.write_text(json.dumps({"status": "needs_review", "tables": review}, ensure_ascii=False, indent=2), encoding="utf-8")
        raise SystemExit(f"Stopped: {len(review)} table(s) need review. Report: {review_path}")

    canonical = {"schema": "financial_canonical_v1", "tables": [canonicalize_table(table) for table in tables]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(canonical, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Saved:", args.output)


if __name__ == "__main__":
    main()
