"""Build complete, provenance-preserving VCI evidence artifacts for the pilot."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "vnstock" / "raw" / "financial"
OUT = ROOT / "data" / "vnstock" / "normalized" / "evidence"
PILOT = ("FPT", "HPG", "MWG", "GAS", "ACB", "MBB", "SSI", "BVH")
STATEMENTS = ("balance_sheet", "income_statement", "cash_flow")
OUTPUT_COLUMNS = ["evidence_id", "ticker", "year", "statement_type", "source", "source_item_id", "source_item_name", "source_item_name_en", "source_row_index", "value", "raw_snapshot_id", "source_file", "created_at"]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def null_value(value: Any) -> Any:
    try:
        return None if bool(pd.isna(value)) else value
    except (TypeError, ValueError):
        return value


def evidence_id(ticker: str, statement: str, snapshot: str, row_index: int, year: int) -> str:
    payload = "|".join(("vnstock_vci", ticker, statement, snapshot, str(row_index), str(year)))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def atomic_write(df: pd.DataFrame, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{destination.stem}.", suffix=".tmp.parquet", dir=destination.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        df.to_parquet(temporary, index=False)
        checked = pd.read_parquet(temporary)
        if list(checked.columns) != OUTPUT_COLUMNS or len(checked) != len(df):
            raise ValueError("evidence temporary artifact validation failed")
        if checked["evidence_id"].duplicated().any():
            raise ValueError("evidence_id is not unique")
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def build_ticker(ticker: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    years: dict[str, list[int]] = {}
    for statement in STATEMENTS:
        path = RAW / ticker / f"{statement}.parquet"
        if not path.is_file():
            raise FileNotFoundError(f"{ticker} {statement}: {path}")
        dataframe = pd.read_parquet(path)
        snapshot = sha256_file(path)
        year_columns = [column for column in dataframe.columns if str(column).strip().isdigit()]
        years[statement] = sorted({int(str(column).strip()) for column in year_columns})
        counts[statement] = len(dataframe)
        item_id = next((column for column in dataframe.columns if str(column).strip().lower() == "item_id"), None)
        item_name = next((column for column in dataframe.columns if str(column).strip().lower() == "item"), None)
        item_name_en = next((column for column in dataframe.columns if str(column).strip().lower() == "item_en"), None)
        if item_id is None:
            raise ValueError(f"{ticker} {statement}: item_id column missing")
        source_file = str(path.relative_to(ROOT))
        created_at = datetime.now(timezone.utc).astimezone().isoformat()
        for source_row_index, source_row in dataframe.iterrows():
            for year_column in year_columns:
                year = int(str(year_column).strip())
                rows.append({
                    "evidence_id": evidence_id(ticker, statement, snapshot, int(source_row_index), year),
                    "ticker": ticker,
                    "year": year,
                    "statement_type": statement,
                    "source": "vnstock_vci",
                    "source_item_id": null_value(source_row[item_id]),
                    "source_item_name": null_value(source_row[item_name]) if item_name else None,
                    "source_item_name_en": null_value(source_row[item_name_en]) if item_name_en else None,
                    "source_row_index": int(source_row_index),
                    "value": null_value(source_row[year_column]),
                    "raw_snapshot_id": snapshot,
                    "source_file": source_file,
                    "created_at": created_at,
                })
    dataframe = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    if dataframe["evidence_id"].duplicated().any():
        raise ValueError(f"{ticker}: duplicate deterministic evidence_id")
    expected = sum(counts[statement] * len(years[statement]) for statement in STATEMENTS)
    if len(dataframe) != expected:
        raise ValueError(f"{ticker}: expected {expected} rows, built {len(dataframe)}")
    return dataframe, {"raw_rows_by_statement": counts, "years_by_statement": years, "expected_rows": expected}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build complete VCI evidence artifacts for the eight-ticker pilot")
    parser.add_argument("--pilot", action="store_true", help="Build all eight pilot tickers")
    parser.add_argument("--only", help="Build one or more pilot tickers, e.g. ACB or ACB,FPT")
    args = parser.parse_args()
    if args.only and args.pilot:
        raise SystemExit("Use either --pilot or --only")
    tickers = [value.strip().upper() for value in args.only.split(",") if value.strip()] if args.only else list(PILOT)
    invalid = sorted(set(tickers) - set(PILOT))
    if invalid:
        raise SystemExit(f"Ticker(s) outside pilot: {', '.join(invalid)}")
    summaries = []
    for ticker in tickers:
        dataframe, detail = build_ticker(ticker)
        atomic_write(dataframe, OUT / f"{ticker}.parquet")
        summaries.append({"ticker": ticker, "rows": len(dataframe), **detail})
        print(json.dumps(summaries[-1], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
