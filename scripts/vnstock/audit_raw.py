"""Read-only audit for downloaded VNStock raw artifacts.

The script never rewrites Parquet/JSON raw data or the download manifest.  It
only reads artifacts and writes audit reports under data/vnstock/metadata/.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = PROJECT_ROOT / "data" / "vnstock"
METADATA_DIR = DATA_ROOT / "metadata"
FINANCIAL_ROOT = DATA_ROOT / "raw" / "financial"
COMPANY_ROOT = DATA_ROOT / "raw" / "company"
MANIFEST_PATH = METADATA_DIR / "download_manifest.csv"
TICKERS_PATH = METADATA_DIR / "tickers.csv"
REPORT_PATH = METADATA_DIR / "raw_audit_report.csv"
SUMMARY_PATH = METADATA_DIR / "raw_audit_summary.json"
SCHEMA_GROUPS_PATH = METADATA_DIR / "raw_schema_groups.csv"
LOG_PATH = DATA_ROOT / "logs" / "raw_audit.log"

FINANCIAL_RESOURCES = {
    "balance_sheet": "balance_sheet.parquet",
    "income_statement": "income_statement.parquet",
    "cash_flow": "cash_flow.parquet",
}
COMPANY_RESOURCES = {
    "profile": "profile.json",
    "overview": "overview.json",
    "officers": "officers.json",
}
YEAR_TARGETS = (2021, 2022, 2023, 2024, 2025)


def configure_logging() -> logging.Logger:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8")],
        force=True,
    )
    return logging.getLogger("raw_audit")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def json_cell(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def bool_or_blank(value: bool | None) -> str:
    return "" if value is None else str(value).lower()


def read_tickers() -> set[str]:
    with TICKERS_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        return {
            row["ticker"].strip().upper()
            for row in csv.DictReader(handle)
            if row.get("ticker") and row["ticker"].strip()
        }


def read_manifest() -> dict[str, dict[str, str]]:
    records: dict[str, dict[str, str]] = {}
    with MANIFEST_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            ticker = (row.get("ticker") or "").strip().upper()
            if ticker:
                records[ticker] = {key: (value or "").strip() for key, value in row.items()}
    return records


def discover_disk_tickers(root: Path) -> set[str]:
    if not root.exists():
        return set()
    return {path.name.upper() for path in root.iterdir() if path.is_dir()}


def base_row(ticker: str, resource: str, statement_type: str, path: Path, manifest_status: str | None) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "resource_type": resource,
        "statement_type": statement_type,
        "manifest_status": manifest_status or "",
        "file_path": str(path.relative_to(PROJECT_ROOT)),
        "file_exists": path.is_file(),
        "file_size_bytes": path.stat().st_size if path.is_file() else 0,
        "readable": False,
        "row_count": None,
        "column_count": None,
        "column_names": [],
        "field_names": [],
        "year_columns": [],
        "earliest_year": None,
        "latest_year": None,
        **{f"has_{year}": None for year in YEAR_TARGETS},
        "item_present": None,
        "item_en_present": None,
        "item_id_present": None,
        "item_id_null_count": None,
        "duplicate_item_id_count": None,
        "person_name_field_present": None,
        "position_field_present": None,
        "empty": None,
        "schema_signature": "",
        "manifest_disk_match": True,
        "error": "",
    }


def audit_parquet(ticker: str, resource: str, filename: str, manifest_status: str | None) -> dict[str, Any]:
    path = FINANCIAL_ROOT / ticker / filename
    row = base_row(ticker, resource, resource, path, manifest_status)
    if not row["file_exists"]:
        row["error"] = "file_missing"
        return row
    try:
        dataframe = pd.read_parquet(path)
        columns = [str(column) for column in dataframe.columns]
        normalized_columns = {column.strip().lower() for column in columns}
        year_columns = [column for column in columns if column.strip().isdigit()]
        years = sorted(int(column.strip()) for column in year_columns)
        item_id_column = next((column for column in dataframe.columns if str(column).strip().lower() == "item_id"), None)
        duplicate_count = None
        null_count = None
        if item_id_column is not None:
            item_ids = dataframe[item_id_column]
            null_count = int(item_ids.isna().sum())
            duplicate_count = int(item_ids.dropna().duplicated().sum())
        metadata_columns = [column for column in columns if column not in year_columns]
        signature_source = {
            "statement_type": resource,
            "metadata_columns": metadata_columns,
            "row_count": int(len(dataframe)),
            "year_count": len(year_columns),
        }
        row.update(
            readable=True,
            row_count=int(len(dataframe)),
            column_count=len(columns),
            column_names=columns,
            year_columns=year_columns,
            earliest_year=years[0] if years else None,
            latest_year=years[-1] if years else None,
            item_present="item" in normalized_columns,
            item_en_present="item_en" in normalized_columns,
            item_id_present=item_id_column is not None,
            item_id_null_count=null_count,
            duplicate_item_id_count=duplicate_count,
            empty=bool(dataframe.empty),
            schema_signature=json_cell(signature_source),
        )
        for year in YEAR_TARGETS:
            row[f"has_{year}"] = str(year) in {column.strip() for column in year_columns}
    except Exception as exc:  # audit must continue even with corrupt artifacts
        row["error"] = f"parquet_read_error: {type(exc).__name__}: {exc}"
    return row


def json_records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in ("data", "items", "result", "results"):
            nested = value.get(key)
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
        return [value]
    return []


def audit_json(ticker: str, resource: str, filename: str, manifest_status: str | None) -> dict[str, Any]:
    path = COMPANY_ROOT / ticker / filename
    row = base_row(ticker, resource, "", path, manifest_status)
    if not row["file_exists"]:
        row["error"] = "file_missing"
        return row
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            payload = json.load(handle)
        records = json_records(payload)
        field_names = sorted({str(key) for record in records for key in record})
        normalized_fields = {field.strip().lower() for field in field_names}
        name_like = any(any(token in field for token in ("name", "person", "officer")) for field in normalized_fields)
        position_like = any(any(token in field for token in ("position", "title", "role", "chuc_vu")) for field in normalized_fields)
        empty = len(records) == 0
        if not records and isinstance(payload, (list, dict)):
            empty = len(payload) == 0
        row.update(
            readable=True,
            row_count=len(records),
            field_names=field_names,
            person_name_field_present=name_like if resource == "officers" else None,
            position_field_present=position_like if resource == "officers" else None,
            empty=empty,
        )
    except Exception as exc:  # audit must continue even with corrupt artifacts
        row["error"] = f"json_read_error: {type(exc).__name__}: {exc}"
    return row


def apply_manifest_consistency(row: dict[str, Any], has_manifest_record: bool) -> None:
    status = row["manifest_status"].lower()
    exists = bool(row["file_exists"])
    usable_data = bool(row["readable"]) and not bool(row["empty"])
    reasons: list[str] = []
    if not has_manifest_record:
        reasons.append("missing_manifest_record")
    elif status in {"success", "exists"} and not exists:
        reasons.append("manifest_nonempty_but_file_missing")
    elif status in {"success", "exists"} and not bool(row["readable"]):
        reasons.append("manifest_nonempty_but_file_unreadable")
    elif status in {"success", "exists"} and bool(row["empty"]):
        reasons.append("manifest_nonempty_but_artifact_empty")
    elif status == "empty" and usable_data:
        reasons.append("manifest_empty_but_artifact_has_data")
    elif status == "error" and usable_data:
        reasons.append("manifest_error_but_artifact_valid")
    elif not status and exists:
        reasons.append("file_exists_without_resource_manifest_status")
    row["manifest_disk_match"] = not reasons
    if reasons:
        row["error"] = "; ".join(filter(None, [row["error"], *reasons]))


def audit_ticker(ticker: str, manifest: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    manifest_record = manifest.get(ticker)
    rows: list[dict[str, Any]] = []
    for resource, filename in FINANCIAL_RESOURCES.items():
        status = manifest_record.get(resource) if manifest_record else None
        row = audit_parquet(ticker, resource, filename, status)
        apply_manifest_consistency(row, manifest_record is not None)
        rows.append(row)
    for resource, filename in COMPANY_RESOURCES.items():
        status = manifest_record.get(resource) if manifest_record else None
        row = audit_json(ticker, resource, filename, status)
        apply_manifest_consistency(row, manifest_record is not None)
        rows.append(row)
    return rows


def resource_counts(rows: list[dict[str, Any]], resource: str) -> dict[str, int]:
    subset = [row for row in rows if row["resource_type"] == resource]
    return {
        "valid": sum(bool(row["readable"]) and not bool(row["empty"]) for row in subset),
        "missing": sum(not bool(row["file_exists"]) for row in subset),
        "empty": sum(bool(row["readable"]) and bool(row["empty"]) for row in subset),
    }


def build_schema_groups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["resource_type"] in FINANCIAL_RESOURCES and row["readable"]:
            groups[(row["resource_type"], row["schema_signature"])].append(row)
    output = []
    for (statement_type, signature), members in sorted(groups.items()):
        output.append(
            {
                "schema_signature": signature,
                "statement_type": statement_type,
                "ticker_count": len(members),
                "sample_tickers": json_cell([member["ticker"] for member in members[:10]]),
                "row_count_range": f"{min(member['row_count'] for member in members)}-{max(member['row_count'] for member in members)}",
                "column_count_range": f"{min(member['column_count'] for member in members)}-{max(member['column_count'] for member in members)}",
                "year_count_range": f"{min(len(member['year_columns']) for member in members)}-{max(len(member['year_columns']) for member in members)}",
            }
        )
    return output


def build_summary(rows: list[dict[str, Any]], tickers: list[str], started_at: str, runtime_seconds: float) -> dict[str, Any]:
    by_ticker: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_ticker[row["ticker"]].append(row)
    financial_complete = financial_partial = financial_empty = 0
    company_complete = company_partial = 0
    for ticker in tickers:
        ticker_rows = {row["resource_type"]: row for row in by_ticker[ticker]}
        financial = [ticker_rows[name] for name in FINANCIAL_RESOURCES]
        company = [ticker_rows[name] for name in COMPANY_RESOURCES]
        financial_is_empty = [row["empty"] or row["manifest_status"].lower() == "empty" for row in financial]
        if all(row["readable"] and not row["empty"] for row in financial):
            financial_complete += 1
        elif all(financial_is_empty):
            financial_empty += 1
        else:
            financial_partial += 1
        if all(row["readable"] and not row["empty"] for row in company):
            company_complete += 1
        else:
            company_partial += 1
    year_coverage = {}
    item_id_coverage = {}
    for resource in FINANCIAL_RESOURCES:
        subset = [row for row in rows if row["resource_type"] == resource and row["readable"]]
        year_coverage[resource] = {
            str(year): sum(bool(row[f"has_{year}"]) for row in subset) for year in YEAR_TARGETS
        }
        item_id_coverage[resource] = {
            "readable_files": len(subset),
            "item_id_present": sum(bool(row["item_id_present"]) for row in subset),
            "item_id_missing": sum(not bool(row["item_id_present"]) for row in subset),
            "item_id_null_values": sum((row["item_id_null_count"] or 0) for row in subset),
            "duplicate_item_id_values": sum((row["duplicate_item_id_count"] or 0) for row in subset),
        }
    counts = {resource: resource_counts(rows, resource) for resource in (*FINANCIAL_RESOURCES, *COMPANY_RESOURCES)}
    schema_groups = build_schema_groups(rows)
    return {
        "tickers_total": len(tickers),
        "financial_complete": financial_complete,
        "financial_partial": financial_partial,
        "financial_empty": financial_empty,
        "company_complete": company_complete,
        "company_partial": company_partial,
        "balance_files_valid": counts["balance_sheet"]["valid"],
        "balance_files_missing": counts["balance_sheet"]["missing"],
        "balance_files_empty": counts["balance_sheet"]["empty"],
        "income_files_valid": counts["income_statement"]["valid"],
        "income_files_missing": counts["income_statement"]["missing"],
        "income_files_empty": counts["income_statement"]["empty"],
        "cashflow_files_valid": counts["cash_flow"]["valid"],
        "cashflow_files_missing": counts["cash_flow"]["missing"],
        "cashflow_files_empty": counts["cash_flow"]["empty"],
        "profile_valid": counts["profile"]["valid"],
        "profile_empty": counts["profile"]["empty"],
        "overview_valid": counts["overview"]["valid"],
        "overview_empty": counts["overview"]["empty"],
        "officers_valid": counts["officers"]["valid"],
        "officers_empty": counts["officers"]["empty"],
        "corrupt_parquet_count": sum("parquet_read_error" in row["error"] for row in rows),
        "corrupt_json_count": sum("json_read_error" in row["error"] for row in rows),
        "manifest_disk_mismatch_count": sum(not row["manifest_disk_match"] for row in rows),
        "statement_schema_groups": schema_groups,
        "year_coverage_summary": year_coverage,
        "item_id_coverage_summary": item_id_coverage,
        "audit_started_at": started_at,
        "audit_finished_at": now_iso(),
        "runtime_seconds": round(runtime_seconds, 3),
    }


def write_reports(rows: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    fieldnames = list(base_row("", "", "", PROJECT_ROOT, "").keys())
    with REPORT_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for original in rows:
            row = original.copy()
            for field in ("column_names", "field_names", "year_columns"):
                row[field] = json_cell(row[field])
            for field in ("file_exists", "readable", "item_present", "item_en_present", "item_id_present", "person_name_field_present", "position_field_present", "empty", "manifest_disk_match"):
                row[field] = bool_or_blank(row[field])
            writer.writerow(row)
    with SUMMARY_PATH.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    schema_groups = summary["statement_schema_groups"]
    with SCHEMA_GROUPS_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["schema_signature", "statement_type", "ticker_count", "sample_tickers", "row_count_range", "column_count_range", "year_count_range"])
        writer.writeheader()
        writer.writerows(schema_groups)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only audit of VNStock raw artifacts.")
    parser.add_argument("--only", help="Audit one ticker (or comma-separated tickers), e.g. ACB")
    parser.add_argument("--limit", type=int, help="Audit the first N tickers after filtering")
    parser.add_argument("--workers", type=int, default=8, help="Local I/O worker count (default: 8)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logger = configure_logging()
    if args.workers < 1:
        raise SystemExit("--workers must be at least 1")
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be at least 1")
    started_at = now_iso()
    started = time.perf_counter()
    manifest = read_manifest()
    tickers = read_tickers() | set(manifest) | discover_disk_tickers(FINANCIAL_ROOT) | discover_disk_tickers(COMPANY_ROOT)
    if args.only:
        requested = {value.strip().upper() for value in args.only.split(",") if value.strip()}
        tickers &= requested
    selected = sorted(tickers)
    if args.limit is not None:
        selected = selected[:args.limit]
    if not selected:
        raise SystemExit("No tickers selected for audit")
    logger.info("Starting read-only raw audit for %d tickers with %d workers", len(selected), args.workers)
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(audit_ticker, ticker, manifest): ticker for ticker in selected}
        for completed, future in enumerate(as_completed(futures), start=1):
            ticker = futures[future]
            try:
                ticker_rows = future.result()
                rows.extend(ticker_rows)
                for row in ticker_rows:
                    if not row["file_exists"] or row["empty"] or not row["manifest_disk_match"]:
                        logger.warning("%s %s: %s", ticker, row["resource_type"], row["error"] or "empty artifact")
                    elif row["error"]:
                        logger.error("%s %s: %s", ticker, row["resource_type"], row["error"])
            except Exception as exc:
                logger.exception("Unexpected audit failure for %s: %s", ticker, exc)
            if completed % 50 == 0 or completed == len(selected):
                logger.info("Audited %d/%d tickers", completed, len(selected))
    rows.sort(key=lambda row: (row["ticker"], list(FINANCIAL_RESOURCES).index(row["resource_type"]) if row["resource_type"] in FINANCIAL_RESOURCES else 3 + list(COMPANY_RESOURCES).index(row["resource_type"])))
    summary = build_summary(rows, selected, started_at, time.perf_counter() - started)
    write_reports(rows, summary)
    logger.info("Audit complete: %s", json.dumps({key: summary[key] for key in ("tickers_total", "corrupt_parquet_count", "corrupt_json_count", "manifest_disk_mismatch_count")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
