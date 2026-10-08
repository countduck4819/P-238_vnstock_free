"""Idempotent pilot loader for complete VCI evidence artifacts."""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "data" / "vnstock" / "normalized" / "evidence"
PILOT = ("FPT", "HPG", "MWG", "GAS", "ACB", "MBB", "SSI", "BVH")
EXPECTED_COLUMNS = ["evidence_id", "ticker", "year", "statement_type", "source", "source_item_id", "source_item_name", "source_item_name_en", "source_row_index", "value", "raw_snapshot_id", "source_file"]


def database_url() -> str:
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            match = re.match(r"^\s*DATABASE_URL\s*=\s*(.*)\s*$", line)
            if match:
                value = match.group(1).strip()
                return value[1:-1] if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'" else value
    raise SystemExit("DATABASE_URL is not configured")


def py_value(value: Any) -> Any:
    if value is None:
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    return value.item() if hasattr(value, "item") else value


def resolve_tickers(args: argparse.Namespace) -> list[str]:
    if args.only:
        tickers = [value.strip().upper() for value in args.only.split(",") if value.strip()]
        invalid = sorted(set(tickers) - set(PILOT))
        if invalid:
            raise SystemExit(f"--only is restricted to pilot tickers: {', '.join(invalid)}")
        return tickers
    return list(PILOT)


def main() -> int:
    parser = argparse.ArgumentParser(description="Load only the eight VCI pilot evidence artifacts")
    parser.add_argument("--pilot", action="store_true", help="Load all eight pilot tickers")
    parser.add_argument("--only", help="Load one or more pilot tickers, e.g. ACB")
    args = parser.parse_args()
    if args.pilot and args.only:
        raise SystemExit("Use either --pilot or --only")
    tickers = resolve_tickers(args)
    with psycopg.connect(database_url(), connect_timeout=5, row_factory=dict_row) as conn:
        db = conn.execute("SELECT current_database() AS database").fetchone()["database"]
        if db != "fireant_stock_dev":
            raise SystemExit(f"Unexpected database: {db}")
        exists = conn.execute("SELECT to_regclass('financial.vnstock_financial_evidence') IS NOT NULL AS exists").fetchone()["exists"]
        if not exists:
            raise SystemExit("Evidence table is absent; apply migration first")
        for ticker in tickers:
            path = EVIDENCE / f"{ticker}.parquet"
            dataframe = pd.read_parquet(path)
            if list(dataframe.columns) != [*EXPECTED_COLUMNS, "created_at"]:
                raise SystemExit(f"{ticker}: unexpected evidence columns")
            if dataframe["evidence_id"].duplicated().any():
                raise SystemExit(f"{ticker}: duplicate evidence_id in artifact")
            before = conn.execute("SELECT count(*) AS count FROM financial.vnstock_financial_evidence WHERE ticker=%s", (ticker,)).fetchone()["count"]
            rows = [tuple(py_value(row[column]) for column in EXPECTED_COLUMNS) for _, row in dataframe.iterrows()]
            try:
                with conn.transaction():
                    with conn.cursor() as cursor:
                        cursor.executemany(
                            """INSERT INTO financial.vnstock_financial_evidence
                            (evidence_id,ticker,year,statement_type,source,source_item_id,source_item_name,source_item_name_en,source_row_index,value,raw_snapshot_id,source_file)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            ON CONFLICT (evidence_id) DO NOTHING""",
                            rows,
                        )
            except Exception:
                # The transaction context rolls back this ticker only.
                raise
            after = conn.execute("SELECT count(*) AS count FROM financial.vnstock_financial_evidence WHERE ticker=%s", (ticker,)).fetchone()["count"]
            if after != len(dataframe):
                raise RuntimeError(f"{ticker}: DB rows {after} != artifact rows {len(dataframe)}")
            print(f"{ticker}: artifact_rows={len(dataframe)}, before={before}, after={after}, inserted={after-before}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
