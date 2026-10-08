"""Compare raw cells with merged OCR candidates using financial equations.

This module never mutates the input mapping and never produces canonical JSON.
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

NUMBER = re.compile(r"^\(?[0-9]{1,3}(?:\.[0-9]{3})*\)?$")


def normalize_label(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("đ", "d")
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_number(value: Any) -> Decimal | None:
    text = str(value or "").strip()
    if not NUMBER.fullmatch(text):
        return None
    negative = text.startswith("(")
    text = text.strip("()").replace(".", "")
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    return -number if negative else number


def candidate_for_validation(value: Any) -> str:
    # Remove OCR whitespace only. Do not add digits or separators.
    text = str(value or "").strip()
    if re.fullmatch(r"[0-9.()\s]+", text):
        return re.sub(r"\s+", "", text)
    return text


def row_matches(name: str, aliases: tuple[str, ...]) -> bool:
    value = normalize_label(name)
    for alias in aliases:
        target = normalize_label(alias)
        if target in value:
            return True
        if SequenceMatcher(None, target, value).ratio() >= 0.62:
            return True
    return False


def find_row(rows: list[list[Any]], aliases: tuple[str, ...]) -> int | None:
    for index, row in enumerate(rows):
        if len(row) > 1 and row_matches(str(row[1]), aliases):
            return index
    return None


def table_source(table: dict[str, Any]) -> dict[str, Any]:
    return table.get("source_grid", table)


def table_key(table: dict[str, Any]) -> str:
    source = table_source(table)
    return str(table.get("table_id", source.get("table_id", "")))


def cell_value(grid: list[list[Any]], row: int | None, column: int) -> Any:
    if row is None or row < 0 or row >= len(grid):
        return None
    return grid[row][column] if 0 <= column < len(grid[row]) else None


def equation_result(rows: list[list[Any]], column: int, aliases: tuple[tuple[str, ...], ...], operation: str) -> dict[str, Any]:
    indexes = [find_row(rows, group) for group in aliases]
    if any(index is None for index in indexes):
        return {"status": "not_applicable", "formula": operation, "rows": indexes}
    values = [parse_number(cell_value(rows, index, column)) for index in indexes]
    if any(value is None for value in values):
        return {"status": "blocked", "formula": operation, "rows": indexes}
    if operation == "revenue_minus_cogs_equals_gross_profit":
        passed = values[0] - values[1] == values[2]
    elif operation == "operating_plus_other_equals_profit_before_tax":
        passed = values[0] + values[1] == values[2]
    elif operation == "total_asset_equals_total_equity_and_liability":
        passed = values[0] == values[1]
    else:
        return {"status": "not_applicable", "formula": operation, "rows": indexes}
    return {"status": "pass" if passed else "fail", "formula": operation, "rows": indexes}


def same_period(left: Any, right: Any) -> bool:
    a = normalize_label(left)
    b = normalize_label(right)
    return bool(a and b and (a == b or SequenceMatcher(None, a, b).ratio() >= 0.78))


def header_path(headers: list[list[Any]], column: int) -> tuple[str, ...]:
    path: list[str] = []
    for header_row in headers:
        value = header_row[column] if column < len(header_row) else None
        if value not in (None, ""):
            path.append(normalize_label(value))
        elif path:
            # Docling leaves merged header coverage empty; carry the parent
            # label forward for physical header-path comparison.
            path.append(path[-1])
    return tuple(path)


def period_context(source: dict[str, Any], grid: list[list[Any]], row: int, column: int, candidate: str) -> dict[str, Any]:
    headers = source.get("headers", [])
    if not headers or row < 0 or row >= len(grid) or column < 0:
        return {"status": "not_applicable", "matches": []}
    current_path = header_path(headers, column)
    if not current_path:
        return {"status": "not_applicable", "matches": []}
    matches = []
    width = max((len(header_row) for header_row in headers), default=0)
    for other_column in range(width):
        if other_column == column or header_path(headers, other_column) != current_path:
            continue
        if other_column >= len(grid[row]):
            continue
        other_value = grid[row][other_column]
        if parse_number(other_value) is not None and parse_number(candidate) == parse_number(other_value):
            matches.append({"column": other_column, "header_path": current_path, "value": other_value})
    return {"status": "corroborated" if matches else "not_corroborated", "header_path": current_path, "matches": matches}


def financial_checks(table: dict[str, Any], grid: list[list[Any]], column: int) -> list[dict[str, Any]]:
    rows = grid
    checks = [
        equation_result(rows, column, (
            ("doanh thu ve ban hang", "doanh thu thuan", "tong doanh thu ve ban hang"),
            ("gia von hang ban",),
            ("loi nhuan gop", "loi nhuan gp", "lqi nhuzn gp"),
        ), "revenue_minus_cogs_equals_gross_profit"),
        equation_result(rows, column, (
            ("loi nhuan thuan tu hoat dong kinh doanh", "operating profit"),
            ("loi nhuan khac", "other profit"),
            ("tong loi nhuan ke toan truoc thue", "profit before tax"),
        ), "operating_plus_other_equals_profit_before_tax"),
        equation_result(rows, column, (
            ("tong tai san", "total asset"),
            ("tong nguon von", "tong von chu so huu va no phai tra", "total equity and liability"),
        ), "total_asset_equals_total_equity_and_liability"),
    ]
    return checks


def finance_state(checks: list[dict[str, Any]]) -> str:
    applicable = [check["status"] for check in checks if check["status"] != "not_applicable"]
    if not applicable:
        return "not_applicable"
    if "fail" in applicable:
        return "fail"
    if "blocked" in applicable:
        return "blocked"
    return "pass"


def relevant_checks(checks: list[dict[str, Any]], row: int | None) -> list[dict[str, Any]]:
    return [check for check in checks if row in check.get("rows", [])]


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate merged OCR candidates against financial equations")
    parser.add_argument("mapping", type=Path)
    parser.add_argument("merged_candidates", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    mapping_document = json.loads(args.mapping.read_text(encoding="utf-8"))
    merged_document = json.loads(args.merged_candidates.read_text(encoding="utf-8"))
    mapping = mapping_document.get("mapping", mapping_document)
    tables = {table_key(table): table for table in mapping.get("tables", [])}

    results: list[dict[str, Any]] = []
    improved_count = 0
    failed_count = 0
    candidate_count = 0

    for item in merged_document.get("items", []):
        candidate = item.get("selected_candidate") or item.get("ocr_value") or ""
        has_candidate = item.get("decision") == "candidate" and bool(candidate)
        if has_candidate:
            candidate_count += 1

        table = tables.get(str(item.get("table", "")))
        raw_value = item.get("old_value")
        raw_status = "valid" if parse_number(raw_value) is not None else "invalid"
        candidate_value = candidate_for_validation(candidate)
        candidate_status = "valid" if parse_number(candidate_value) is not None else "invalid"

        raw_finance = "not_applicable"
        candidate_finance = "not_applicable"
        context = {"status": "not_applicable", "matches": []}
        raw_checks: list[dict[str, Any]] = []
        candidate_checks: list[dict[str, Any]] = []
        row = item.get("row")
        column = item.get("column")
        if table is not None and isinstance(row, int) and isinstance(column, int):
            source = table_source(table)
            original_grid = source.get("rows", [])
            raw_checks = financial_checks(table, original_grid, column)
            candidate_grid = deepcopy(original_grid)
            if has_candidate and 0 <= row < len(candidate_grid) and 0 <= column < len(candidate_grid[row]):
                candidate_grid[row][column] = candidate_value
            candidate_checks = financial_checks(table, candidate_grid, column)
            raw_finance = finance_state(raw_checks)
            candidate_finance = finance_state(candidate_checks)
            if has_candidate:
                context = period_context(source, original_grid, row, column, candidate_value)

        raw_relevant = relevant_checks(raw_checks, row)
        candidate_relevant = relevant_checks(candidate_checks, row)
        raw_relevant_state = finance_state(raw_relevant)
        candidate_relevant_state = finance_state(candidate_relevant)
        numeric_improved = has_candidate and raw_status == "invalid" and candidate_status == "valid"
        formula_improved = any(
            check.get("status") == "pass"
            for check in candidate_relevant
        ) and not any(check.get("status") == "pass" for check in raw_relevant)
        improved = bool(numeric_improved or formula_improved)
        if improved:
            improved_count += 1
        if has_candidate and candidate_relevant_state == "fail":
            failed_count += 1

        # A parse improvement alone is not enough to approve a financial cell.
        # Approval requires an applicable equation to pass for this row/column.
        approved = candidate_value if candidate_relevant_state == "pass" else ""
        if approved:
            reason = "candidate_passes_applicable_financial_equation"
        elif improved and candidate_relevant_state == "fail":
            reason = "numeric_improved_but_candidate_breaks_financial_equation"
        elif improved and candidate_relevant_state == "blocked":
            reason = "numeric_improved_but_financial_equation_blocked"
        elif improved:
            reason = "numeric_or_financial_validation_improved_but_not_approved"
        elif not has_candidate:
            reason = "no_approved_candidate"
        elif candidate_status != "valid":
            reason = "candidate_numeric_format_invalid"
        elif candidate_finance == "fail":
            reason = "candidate_breaks_financial_equation"
        elif candidate_finance == "blocked":
            reason = "financial_equation_blocked_by_other_cells"
        else:
            reason = "candidate_does_not_improve_validation"

        results.append({
            "page": item.get("page"),
            "table": item.get("table"),
            "row": row,
            "column": column,
            "raw_value": raw_value,
            "candidate_value": candidate,
            "validation_candidate": candidate_value,
            "raw_status": raw_status,
            "candidate_status": candidate_status,
            "raw_finance_status": raw_finance,
            "candidate_finance_status": candidate_finance,
            "period_context": context,
            "raw_relevant_finance_status": raw_relevant_state,
            "candidate_relevant_finance_status": candidate_relevant_state,
            "numeric_improved": numeric_improved,
            "formula_improved": formula_improved,
            "raw_checks": raw_checks,
            "candidate_checks": candidate_checks,
            "improved": improved,
            "approved_candidate": approved,
            "reason": reason,
            "confidence": item.get("confidence"),
            "method": item.get("method", "RapidOCR"),
            "bbox": item.get("bbox"),
            "selected_source": item.get("selected_source"),
        })

    recommendation = (
        "review_improved_candidates_before_apply"
        if improved_count
        else "keep_pending_review_and_retry_or_manual_verify"
    )
    report = {
        "schema": "financial_validation_v3",
        "policy": {"raw_value_overwrite": False, "mapping_mutation": False, "canonical_output": False},
        "items": results,
        "summary": {
            "total_cells": len(results),
            "candidate_cells": candidate_count,
            "finance_improved": improved_count,
            "finance_failed": failed_count,
            "approved_candidates": sum(bool(item["approved_candidate"]) for item in results),
            "numeric_improved": sum(item["numeric_improved"] for item in results),
            "formula_improved": sum(item["formula_improved"] for item in results),
            "context_corroborated": sum(item["period_context"]["status"] == "corroborated" for item in results),
            "recommendation": recommendation,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Saved:", args.output)
    print(report["summary"])


if __name__ == "__main__":
    main()
