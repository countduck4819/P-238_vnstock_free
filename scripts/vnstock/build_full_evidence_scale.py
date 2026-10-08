"""Build lossless VCI evidence artifacts for every ticker with local raw data."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "vnstock"
RAW = DATA / "raw" / "financial"
OUT = DATA / "normalized" / "evidence"
META = DATA / "metadata"
MANIFEST = META / "evidence_manifest.csv"
LOG = DATA / "logs" / "evidence_scale.log"
STATEMENTS = ("balance_sheet", "income_statement", "cash_flow")
PILOT = ("FPT", "HPG", "MWG", "GAS", "ACB", "MBB", "SSI", "BVH")


def env_logger() -> logging.Logger:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=[logging.FileHandler(LOG, encoding="utf-8")], force=True)
    return logging.getLogger("evidence_scale")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def null_value(value: Any) -> Any:
    try:
        return None if bool(pd.isna(value)) else (value.item() if hasattr(value, "item") else value)
    except (TypeError, ValueError):
        return value


def evidence_id(ticker: str, statement: str, snapshot: str, row_index: int, year: int) -> str:
    return hashlib.sha256("|".join(("vnstock_vci", ticker, statement, snapshot, str(row_index), str(year))).encode()).hexdigest()


def atomic_write(frame: pd.DataFrame, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{destination.stem}.", suffix=".tmp.parquet", dir=destination.parent)
    os.close(fd); temporary = Path(name)
    try:
        frame.to_parquet(temporary, index=False)
        checked = pd.read_parquet(temporary)
        if len(checked) != len(frame) or checked["evidence_id"].duplicated().any():
            raise ValueError("temporary evidence validation failed")
        os.replace(temporary, destination)
    finally:
        if temporary.exists(): temporary.unlink()


def read_tickers() -> list[str]:
    with (META / "tickers.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        return sorted({row["ticker"].strip().upper() for row in csv.DictReader(handle) if row.get("ticker", "").strip()})


def build_one(ticker: str, logger: logging.Logger) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    statements_loaded: list[str] = []
    snapshots: set[str] = set()
    source_ids: set[str] = set()
    errors: list[str] = []
    for statement in STATEMENTS:
        path = RAW / ticker / f"{statement}.parquet"
        if not path.is_file():
            errors.append(f"{statement}:file_missing")
            continue
        try:
            frame = pd.read_parquet(path)
            statements_loaded.append(statement)
            snapshot = sha256(path); snapshots.add(snapshot)
            year_columns = [column for column in frame.columns if str(column).strip().isdigit()]
            item_id = next((column for column in frame.columns if str(column).strip().lower() == "item_id"), None)
            item = next((column for column in frame.columns if str(column).strip().lower() == "item"), None)
            item_en = next((column for column in frame.columns if str(column).strip().lower() == "item_en"), None)
            if item_id is None:
                errors.append(f"{statement}:item_id_missing"); continue
            for source_row_index, source_row in frame.iterrows():
                source_item_id = null_value(source_row[item_id])
                if source_item_id is not None: source_ids.add(str(source_item_id))
                for year_column in year_columns:
                    year = int(str(year_column).strip())
                    rows.append({"evidence_id": evidence_id(ticker, statement, snapshot, int(source_row_index), year), "ticker": ticker, "year": year, "statement_type": statement, "source": "vnstock_vci", "source_item_id": source_item_id, "source_item_name": null_value(source_row[item]) if item else None, "source_item_name_en": null_value(source_row[item_en]) if item_en else None, "source_row_index": int(source_row_index), "value": null_value(source_row[year_column]), "raw_snapshot_id": snapshot, "source_file": str(path.relative_to(ROOT)), "created_at": datetime.now(timezone.utc).astimezone().isoformat()})
        except Exception as exc:
            errors.append(f"{statement}:{type(exc).__name__}:{exc}")
            logger.error("%s %s: %s", ticker, statement, exc)
    frame = pd.DataFrame(rows, columns=["evidence_id", "ticker", "year", "statement_type", "source", "source_item_id", "source_item_name", "source_item_name_en", "source_row_index", "value", "raw_snapshot_id", "source_file", "created_at"])
    status = "success" if len(statements_loaded) == 3 else "partial" if statements_loaded else "empty"
    if errors and not statements_loaded:
        status = "empty" if all(error.endswith(":file_missing") for error in errors) else "error"
    if rows: atomic_write(frame, OUT / f"{ticker}.parquet")
    elif status == "empty":
        output = OUT / f"{ticker}.parquet"
        if output.exists(): output.unlink()
    years = sorted(frame["year"].unique().tolist()) if not frame.empty else []
    result = {"ticker": ticker, "status": status, "statements_loaded": json.dumps(statements_loaded), "evidence_rows": len(frame), "year_min": min(years) if years else "", "year_max": max(years) if years else "", "source_item_count": len(source_ids), "null_value_count": int(frame["value"].isna().sum()) if not frame.empty else 0, "raw_snapshot_count": len(snapshots), "last_error": "; ".join(errors), "updated_at": datetime.now(timezone.utc).astimezone().isoformat()}
    logger.info("%s status=%s statements=%s rows=%d", ticker, status, statements_loaded, len(frame))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Build VCI evidence artifacts for all local raw financial tickers")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--only")
    args = parser.parse_args()
    if args.workers < 1: raise SystemExit("--workers must be >= 1")
    logger = env_logger(); tickers = read_tickers()
    if args.only:
        selected = [value.strip().upper() for value in args.only.split(",") if value.strip()]
        unknown = sorted(set(selected) - set(tickers))
        if unknown: raise SystemExit(f"Unknown tickers: {', '.join(unknown)}")
        tickers = selected
    start = time.perf_counter(); results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(build_one, ticker, logger): ticker for ticker in tickers}
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda row: row["ticker"]); META.mkdir(parents=True, exist_ok=True)
    with MANIFEST.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["ticker", "status", "statements_loaded", "evidence_rows", "year_min", "year_max", "source_item_count", "null_value_count", "raw_snapshot_count", "last_error", "updated_at"]); writer.writeheader(); writer.writerows(results)
    logger.info("Finished %d tickers in %.2fs", len(results), time.perf_counter() - start)
    print(json.dumps({"tickers": len(results), "success": sum(row["status"] == "success" for row in results), "partial": sum(row["status"] == "partial" for row in results), "empty": sum(row["status"] == "empty" for row in results), "error": sum(row["status"] == "error" for row in results), "rows": sum(row["evidence_rows"] for row in results), "runtime_seconds": round(time.perf_counter() - start, 3)}, ensure_ascii=False))
    return 0


if __name__ == "__main__": raise SystemExit(main())
