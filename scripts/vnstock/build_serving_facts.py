"""Materialize approved canonical mappings into serving facts (pilot only)."""

from __future__ import annotations

import argparse
import csv
import os
import re
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[2]
META = ROOT / "data" / "vnstock" / "metadata"
CATALOG = META / "canonical_metric_catalog.csv"
MAPPINGS = META / "source_metric_mapping_pilot.csv"
PILOT = ("FPT", "HPG", "MWG", "GAS", "ACB", "MBB", "SSI", "BVH")


def env_url() -> str:
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        match = re.match(r"^DATABASE_URL\s*=\s*(.*)$", line)
        if match:
            value = match.group(1).strip()
            return value[1:-1] if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'" else value
    raise SystemExit("DATABASE_URL is not configured")


def py(value: Any) -> Any:
    if value is None:
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    return value.item() if hasattr(value, "item") else value


def main() -> int:
    parser = argparse.ArgumentParser(description="Build pilot canonical serving facts from approved DB mappings")
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--only", help="One or more pilot tickers")
    args = parser.parse_args()
    if args.pilot and args.only:
        raise SystemExit("Use either --pilot or --only")
    tickers = [v.strip().upper() for v in args.only.split(",") if v.strip()] if args.only else list(PILOT)
    if set(tickers) - set(PILOT):
        raise SystemExit("Only the eight pilot tickers are allowed")
    with MAPPINGS.open("r", encoding="utf-8", newline="") as handle:
        mappings = list(csv.DictReader(handle))
    approved = [row for row in mappings if row["mapping_status"] == "APPROVED" and row["ticker_scope"] in tickers]
    with CATALOG.open("r", encoding="utf-8", newline="") as handle:
        catalog = list(csv.DictReader(handle))
    with psycopg.connect(env_url(), connect_timeout=5, row_factory=dict_row) as conn:
        db = conn.execute("SELECT current_database() AS database").fetchone()["database"]
        if db != "fireant_stock_dev":
            raise SystemExit(f"Unexpected database: {db}")
        for row in catalog:
            conn.execute("""INSERT INTO financial.vnstock_metric_catalog
                (canonical_metric_code,metric_name_vi,metric_name_en,statement_type,unit_type,description)
                VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (canonical_metric_code) DO NOTHING""",
                (row["canonical_metric_code"], row["metric_name_vi"], row["metric_name_en"], row["statement_type"], row["unit_type"], row["description"]))
        for row in mappings:
            conn.execute("""INSERT INTO financial.vnstock_metric_mapping
                (mapping_id,source,ticker_scope,statement_type,source_item_id,source_item_name,source_item_name_en,source_row_index,canonical_metric_code,mapping_version,mapping_status,notes)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (mapping_id) DO NOTHING""",
                (row["mapping_id"], row["source"], row["ticker_scope"], row["statement_type"], row["source_item_id"], row["source_item_name"], row["source_item_name_en"] or None, int(row["source_row_index"]), row["canonical_metric_code"], int(row["mapping_version"]), row["mapping_status"], row["notes"]))
        conn.commit()
        for ticker in tickers:
            ticker_mappings = [row for row in approved if row["ticker_scope"] == ticker]
            serving_rows = []
            with conn.transaction():
                for mapping in ticker_mappings:
                    evidence = conn.execute("""SELECT evidence_id, year, value FROM financial.vnstock_financial_evidence
                        WHERE ticker=%s AND statement_type=%s AND source=%s AND source_item_id=%s AND source_row_index=%s
                        ORDER BY year""", (ticker, mapping["statement_type"], mapping["source"], mapping["source_item_id"], int(mapping["source_row_index"]))).fetchall()
                    if len(evidence) != 8 or len({row["year"] for row in evidence}) != 8:
                        raise RuntimeError(f"{ticker}/{mapping['canonical_metric_code']}: selector returned {len(evidence)} evidence rows, expected 8")
                    for evidence_row in evidence:
                        serving_rows.append((ticker, evidence_row["year"], mapping["canonical_metric_code"], py(evidence_row["value"]), evidence_row["evidence_id"], mapping["mapping_id"]))
                with conn.cursor() as cursor:
                    cursor.executemany("""INSERT INTO financial.vnstock_serving_facts
                        (ticker,year,canonical_metric_code,value,source_evidence_id,mapping_id)
                        VALUES (%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (ticker,year,canonical_metric_code) DO NOTHING""", serving_rows)
            count = conn.execute("SELECT count(*) AS count FROM financial.vnstock_serving_facts WHERE ticker=%s", (ticker,)).fetchone()["count"]
            expected = len(serving_rows)
            if count != expected:
                raise RuntimeError(f"{ticker}: serving rows {count} != expected {expected}")
            print(f"{ticker}: approved_mappings={len(ticker_mappings)}, serving_rows={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
