import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(BASE_DIR, "output", "raw", "page_005_table_grid.json")
OUTPUT_FILE = os.path.join(
    BASE_DIR, "output", "canonical", "FPT", "Q1_2015", "financial_fact.json"
)
REVIEW_FILE = os.path.join(
    BASE_DIR, "output", "canonical", "FPT", "Q1_2015", "financial_fact_needs_review.json"
)

DOCUMENT = {
    "ticker": "FPT",
    "document_id": "FPT_Q1_2015",
    "source_pdf": "FPT_Q1_2015.pdf",
    "report_period": "Q1_2015",
    "company_name": "Công ty Cổ phần FPT",
    "exchange": "HOSE",
}


def normalize_value(raw):
    if raw is None or str(raw).strip() == "":
        return None
    text = str(raw).strip()
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    try:
        value = int(text.replace(".", "").replace(",", ""))
        return -value if negative else value
    except ValueError:
        return None


def find_header_index(grid):
    for index, row in enumerate(grid):
        labels = {str(cell).strip().lower() for cell in row if cell is not None}
        if "mã số" in labels and ("năm nay" in labels or "năm trước" in labels):
            return index
    return None


def validate_grid(grid):
    errors = []
    if not isinstance(grid, list) or not grid:
        return ["grid is empty"]
    if not all(isinstance(row, list) for row in grid):
        return ["every grid row must be an array"]

    header_index = find_header_index(grid)
    if header_index is None:
        errors.append("financial header not found")
        return errors

    header_length = len(grid[header_index])
    if header_length == 0:
        errors.append("header is empty")
        return errors

    for offset, row in enumerate(grid[header_index + 1:], start=header_index + 1):
        if len(row) != header_length:
            errors.append(
                f"row {offset} has {len(row)} columns; expected {header_length}"
            )
    return errors


def convert(data):
    grid = data.get("grid", [])
    errors = validate_grid(grid)
    if errors:
        return {
            "status": "needs_review",
            "errors": errors,
            "source_grid": data,
        }

    header_index = find_header_index(grid)
    header = ["" if cell is None else str(cell).strip() for cell in grid[header_index]]
    name_index = next(
        (i for i, value in enumerate(header) if value.upper() in {"CHỈ TIÊU", "CHI TIÊU", "CHI TIỂU"}),
        None,
    )
    code_index = next(
        (i for i, value in enumerate(header) if value.upper() == "MÃ SỐ"),
        None,
    )
    value_indices = [
        i for i, value in enumerate(header)
        if value.upper() in {"NĂM NAY", "NĂM TRƯỚC"}
    ]
    if name_index is None or code_index is None or not value_indices:
        return {
            "status": "needs_review",
            "errors": ["required financial columns not found"],
            "source_grid": data,
        }

    rows = []
    for row in grid[header_index + 1:]:
        if all(cell in (None, "") for cell in row):
            continue
        row_name = row[name_index]
        if row_name in (None, ""):
            continue
        cells = []
        for index in value_indices:
            raw = row[index]
            cells.append({
                "column": header[index],
                "raw_value": raw,
                "normalized_value": normalize_value(raw),
                "source": {
                    "pdf": DOCUMENT["source_pdf"],
                    "page": data.get("source", {}).get("page", ""),
                    "table": "",
                    "row": row_name,
                    "column": header[index],
                    "method": "Qwen2.5-VL-3B-Instruct",
                },
            })
        rows.append({"row_name": row_name, "row_code": row[code_index], "cells": cells})

    return {
        "document": DOCUMENT,
        "statement": {
            "statement_type": "income_statement",
            "table_name": "",
            "period": "",
            "unit": "",
        },
        "rows": rows,
    }


with open(INPUT_FILE, encoding="utf-8") as file:
    data = json.load(file)

if "error" in data:
    raise ValueError(data["error"])

result = convert(data)
os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
if result.get("status") == "needs_review":
    with open(REVIEW_FILE, "w", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
    raise SystemExit(f"needs_review: {REVIEW_FILE}")

with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
    json.dump(result, file, ensure_ascii=False, indent=2)
print("Saved:", OUTPUT_FILE)
