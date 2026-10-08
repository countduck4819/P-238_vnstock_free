"""Normalize the reviewed VNStock financial pilot from wide to long format.

This module is deliberately limited to the eight roadmap pilot tickers.  Raw
Parquet files are read only; duplicate logical keys are recorded as evidence
and excluded from the canonical artifact rather than resolved silently.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_ROOT = PROJECT_ROOT / "data" / "vnstock" / "raw" / "financial"
NORMALIZED_ROOT = PROJECT_ROOT / "data" / "vnstock" / "normalized" / "facts"
METADATA_ROOT = PROJECT_ROOT / "data" / "vnstock" / "metadata"
LOG_ROOT = PROJECT_ROOT / "data" / "vnstock" / "logs"
MANIFEST_PATH = METADATA_ROOT / "normalization_manifest.csv"
CONFLICT_PATH = METADATA_ROOT / "normalization_conflicts.csv"
LOG_PATH = LOG_ROOT / "normalizer.log"

PILOT_TICKERS = ("FPT", "HPG", "MWG", "GAS", "ACB", "MBB", "SSI", "BVH")
STATEMENTS = ("balance_sheet", "income_statement", "cash_flow")
OUTPUT_COLUMNS = [
    "ticker", "year", "statement_type", "metric_code", "metric_name",
    "metric_name_en", "value", "source",
]
CONFLICT_COLUMNS = [
    "ticker", "statement_type", "year", "metric_code", "metric_name",
    "source_row_index", "value", "conflict_type",
]
MANIFEST_COLUMNS = [
    "ticker", "status", "raw_statements_found", "normalized_rows", "years_found",
    "metric_count", "duplicate_conflict_count", "null_value_count",
    "raw_rows_by_statement", "detected_years_by_statement", "raw_timestamps_unchanged",
    "last_error", "updated_at",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def json_cell(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def configure_logging() -> logging.Logger:
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8")],
        force=True,
    )
    return logging.getLogger("normalizer")


def is_null(value: Any) -> bool:
    try:
        result = pd.isna(value)
        return bool(result) if not hasattr(result, "__len__") else False
    except (TypeError, ValueError):
        return value is None


def value_for_record(value: Any) -> Any:
    return None if is_null(value) else value


def atomic_write_parquet(dataframe: pd.DataFrame, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{destination.stem}.", suffix=".tmp.parquet", dir=destination.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        dataframe.to_parquet(temporary, index=False)
        # Read the temporary artifact before replacing the final artifact.
        checked = pd.read_parquet(temporary)
        if list(checked.columns) != OUTPUT_COLUMNS or len(checked) != len(dataframe):
            raise ValueError("temporary Parquet validation failed")
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def raw_timestamps(paths: list[Path]) -> dict[str, int | None]:
    return {str(path): (path.stat().st_mtime_ns if path.is_file() else None) for path in paths}


def normalize_ticker(ticker: str, logger: logging.Logger) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    ticker = ticker.upper()
    started = time.perf_counter()
    raw_paths = [RAW_ROOT / ticker / f"{statement}.parquet" for statement in STATEMENTS]
    before_timestamps = raw_timestamps(raw_paths)
    records: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    raw_rows_by_statement: dict[str, int] = {}
    years_by_statement: dict[str, list[int]] = {}
    errors: list[str] = []
    found_statements: list[str] = []
    for statement, path in zip(STATEMENTS, raw_paths):
        if not path.is_file():
            errors.append(f"{statement}: file_missing")
            continue
        try:
            dataframe = pd.read_parquet(path)
            found_statements.append(statement)
            year_columns = [column for column in dataframe.columns if str(column).strip().isdigit()]
            years = sorted({int(str(column).strip()) for column in year_columns})
            years_by_statement[statement] = years
            raw_rows_by_statement[statement] = len(dataframe)
            item_id_column = next((column for column in dataframe.columns if str(column).strip().lower() == "item_id"), None)
            item_column = next((column for column in dataframe.columns if str(column).strip().lower() == "item"), None)
            item_en_column = next((column for column in dataframe.columns if str(column).strip().lower() == "item_en"), None)
            if item_id_column is None:
                errors.append(f"{statement}: item_id_column_missing")
                continue
            for source_index, source_row in dataframe.iterrows():
                metric_code = value_for_record(source_row[item_id_column])
                metric_name = value_for_record(source_row[item_column]) if item_column is not None else None
                metric_name_en = value_for_record(source_row[item_en_column]) if item_en_column is not None else None
                for year_column in year_columns:
                    value = value_for_record(source_row[year_column])
                    records.append({
                        "ticker": ticker,
                        "year": int(str(year_column).strip()),
                        "statement_type": statement,
                        "metric_code": metric_code,
                        "metric_name": metric_name,
                        "metric_name_en": metric_name_en,
                        "value": value,
                        "source": "vnstock_vci",
                        "_source_row_index": int(source_index),
                    })
        except Exception as exc:
            errors.append(f"{statement}: {type(exc).__name__}: {exc}")
            logger.error("%s %s read failed: %s", ticker, statement, exc)

    candidate = pd.DataFrame(records)
    if candidate.empty:
        duplicate_mask = pd.Series([], dtype=bool)
    else:
        logical_columns = ["ticker", "year", "statement_type", "metric_code"]
        duplicate_mask = candidate.duplicated(logical_columns, keep=False)
        if duplicate_mask.any():
            duplicate_rows = candidate.loc[duplicate_mask]
            for _, duplicate in duplicate_rows.iterrows():
                conflicts.append({
                    "ticker": duplicate["ticker"],
                    "statement_type": duplicate["statement_type"],
                    "year": duplicate["year"],
                    "metric_code": duplicate["metric_code"],
                    "metric_name": duplicate["metric_name"],
                    "source_row_index": duplicate["_source_row_index"],
                    "value": duplicate["value"],
                    "conflict_type": "duplicate_logical_key",
                })
            logger.warning("%s: %d duplicate rows across %d logical keys", ticker, int(duplicate_mask.sum()), int(candidate.loc[duplicate_mask].groupby(logical_columns, dropna=False).ngroups))
    canonical = candidate.loc[~duplicate_mask].drop(columns=["_source_row_index"], errors="ignore")
    if not canonical.empty:
        canonical = canonical[OUTPUT_COLUMNS]
    else:
        canonical = pd.DataFrame(columns=OUTPUT_COLUMNS)
    destination = NORMALIZED_ROOT / f"{ticker}.parquet"
    status = "success"
    if errors and found_statements:
        status = "partial"
    elif errors:
        status = "error"
    if conflicts:
        status = "conflict"
    try:
        atomic_write_parquet(canonical, destination)
    except Exception as exc:
        errors.append(f"output: {type(exc).__name__}: {exc}")
        status = "error"
    unchanged = before_timestamps == raw_timestamps(raw_paths)
    if not unchanged:
        errors.append("raw_timestamp_changed_unexpectedly")
    all_years = sorted({year for years in years_by_statement.values() for year in years})
    summary = {
        "ticker": ticker,
        "status": status,
        "raw_statements_found": json_cell(found_statements),
        "normalized_rows": len(canonical),
        "years_found": json_cell(all_years),
        "metric_count": int(candidate["metric_code"].nunique(dropna=True)) if not candidate.empty else 0,
        "duplicate_conflict_count": int(candidate.loc[duplicate_mask].groupby(["ticker", "year", "statement_type", "metric_code"], dropna=False).ngroups) if duplicate_mask.any() else 0,
        "null_value_count": int(candidate["value"].isna().sum()) if not candidate.empty else 0,
        "raw_rows_by_statement": json_cell(raw_rows_by_statement),
        "detected_years_by_statement": json_cell(years_by_statement),
        "raw_timestamps_unchanged": str(unchanged).lower(),
        "last_error": "; ".join(errors),
        "updated_at": now_iso(),
    }
    logger.info("%s status=%s raw_rows=%s normalized_rows=%d conflicts=%d runtime=%.3fs", ticker, status, raw_rows_by_statement, len(canonical), summary["duplicate_conflict_count"], time.perf_counter() - started)
    return summary, conflicts


def write_manifest(rows: list[dict[str, Any]]) -> None:
    METADATA_ROOT.mkdir(parents=True, exist_ok=True)
    with MANIFEST_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def write_conflicts(conflicts: list[dict[str, Any]]) -> None:
    METADATA_ROOT.mkdir(parents=True, exist_ok=True)
    with CONFLICT_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CONFLICT_COLUMNS)
        writer.writeheader()
        writer.writerows(conflicts)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize only the reviewed eight-ticker financial pilot.")
    parser.add_argument("--pilot", action="store_true", help="Normalize the eight roadmap pilot tickers")
    parser.add_argument("--only", help="Normalize one pilot ticker, e.g. ACB")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logger = configure_logging()
    if args.only and args.pilot:
        raise SystemExit("Use either --pilot or --only, not both")
    if args.only:
        tickers = [value.strip().upper() for value in args.only.split(",") if value.strip()]
        invalid = sorted(set(tickers) - set(PILOT_TICKERS))
        if invalid:
            raise SystemExit(f"--only is restricted to pilot tickers; invalid: {', '.join(invalid)}")
    else:
        # No argument also means pilot; there is intentionally no full-universe default.
        tickers = list(PILOT_TICKERS)
    started = time.perf_counter()
    logger.info("Starting normalization pilot: %s", ", ".join(tickers))
    summaries: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for ticker in tickers:
        summary, ticker_conflicts = normalize_ticker(ticker, logger)
        summaries.append(summary)
        conflicts.extend(ticker_conflicts)
    write_manifest(summaries)
    write_conflicts(conflicts)
    logger.info("Normalization finished: %d ticker(s), %d conflict rows, %.3fs", len(tickers), len(conflicts), time.perf_counter() - started)
    return 0 if all(row["status"] in {"success", "conflict", "partial"} for row in summaries) else 1


if __name__ == "__main__":
    raise SystemExit(main())
