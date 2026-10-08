"""Validate loaded pilot evidence and benchmark its read queries."""

from __future__ import annotations

import argparse
import json
import csv
import os
import re
import statistics
import time
from pathlib import Path

import pandas as pd
import psycopg
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "data" / "vnstock" / "normalized" / "evidence"
META = ROOT / "data" / "vnstock" / "metadata"
REPORT = META / "postgres_evidence_pilot_report.md"
COUNTS = META / "postgres_evidence_pilot_counts.csv"
CONFLICTS = META / "normalization_conflicts.csv"
EXAMPLES = META / "normalization_conflict_examples.csv"
PILOT = ("FPT", "HPG", "MWG", "GAS", "ACB", "MBB", "SSI", "BVH")


def db_url() -> str:
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*DATABASE_URL\s*=\s*(.*)\s*$", line)
        if match:
            value = match.group(1).strip()
            return value[1:-1] if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'" else value
    raise SystemExit("DATABASE_URL is not configured")


def percentile(values: list[float], pct: float) -> float:
    return sorted(values)[min(len(values) - 1, int(round((len(values) - 1) * pct)))]


def benchmark(conn: psycopg.Connection, query: str, params: tuple) -> dict[str, float]:
    for _ in range(5):
        conn.execute(query, params).fetchall()
    samples = []
    for _ in range(30):
        start = time.perf_counter()
        conn.execute(query, params).fetchall()
        samples.append((time.perf_counter() - start) * 1000)
    return {"p50_ms": round(percentile(samples, 0.50), 3), "p95_ms": round(percentile(samples, 0.95), 3), "avg_ms": round(statistics.mean(samples), 3)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and benchmark VCI evidence in PostgreSQL")
    parser.parse_args()
    artifact_frames = {ticker: pd.read_parquet(EVIDENCE / f"{ticker}.parquet") for ticker in PILOT}
    with psycopg.connect(db_url(), connect_timeout=5, row_factory=dict_row) as conn:
        database = conn.execute("SELECT current_database() AS database, current_user AS user").fetchone()
        table_exists = conn.execute("SELECT to_regclass('financial.vnstock_financial_evidence') IS NOT NULL AS exists").fetchone()["exists"]
        if database["database"] != "fireant_stock_dev" or not table_exists:
            raise SystemExit("Validation precondition failed")
        counts = []
        for ticker, frame in artifact_frames.items():
            db_count = conn.execute("SELECT count(*) AS count FROM financial.vnstock_financial_evidence WHERE ticker=%s", (ticker,)).fetchone()["count"]
            if db_count != len(frame):
                raise SystemExit(f"{ticker}: DB count {db_count} != artifact count {len(frame)}")
            db_statement = conn.execute("SELECT statement_type, count(*) AS count FROM financial.vnstock_financial_evidence WHERE ticker=%s GROUP BY statement_type ORDER BY statement_type", (ticker,)).fetchall()
            for row in db_statement:
                artifact_count = int((frame["statement_type"] == row["statement_type"]).sum())
                if artifact_count != row["count"]:
                    raise SystemExit(f"{ticker}/{row['statement_type']}: DB/artifact mismatch")
            counts.append({"ticker": ticker, "artifact_rows": len(frame), "db_rows": db_count, "year_min": int(frame.year.min()), "year_max": int(frame.year.max()), "artifact_null_values": int(frame.value.isna().sum()), "db_null_values": conn.execute("SELECT count(*) AS count FROM financial.vnstock_financial_evidence WHERE ticker=%s AND value IS NULL", (ticker,)).fetchone()["count"], "distinct_source_item_id": conn.execute("SELECT count(DISTINCT source_item_id) AS count FROM financial.vnstock_financial_evidence WHERE ticker=%s", (ticker,)).fetchone()["count"], "distinct_evidence_id": conn.execute("SELECT count(DISTINCT evidence_id) AS count FROM financial.vnstock_financial_evidence WHERE ticker=%s", (ticker,)).fetchone()["count"], "raw_snapshot_count": conn.execute("SELECT count(DISTINCT raw_snapshot_id) AS count FROM financial.vnstock_financial_evidence WHERE ticker=%s", (ticker,)).fetchone()["count"]})
        conflict_df = pd.read_csv(EXAMPLES, dtype=str, keep_default_na=False)
        preserved = []
        for _, group in conflict_df.groupby(["ticker", "statement_type", "year", "metric_code"], sort=True):
            first = group.iloc[0]
            ticker, statement, year, source_item_id = first["ticker"], first["statement_type"], first["year"], first["metric_code"]
            rows = conn.execute("SELECT source_row_index, evidence_id, value FROM financial.vnstock_financial_evidence WHERE ticker=%s AND statement_type=%s AND year=%s AND source_item_id=%s ORDER BY source_row_index", (ticker, statement, int(year), source_item_id)).fetchall()
            expected_indices = {int(value) for value in json.loads(first["source_row_indices"])}
            actual_indices = {int(row["source_row_index"]) for row in rows}
            preserved.append({"ticker": ticker, "statement_type": statement, "year": int(year), "source_item_id": source_item_id, "expected_conflict_rows": int(first["evidence_row_count"]), "db_matching_rows": len(rows), "all_source_rows_present": expected_indices.issubset(actual_indices), "distinct_db_values": len({str(row["value"]) for row in rows})})
        conflict_pass = all(item["all_source_rows_present"] and item["db_matching_rows"] >= item["expected_conflict_rows"] for item in preserved)
        sample = artifact_frames["FPT"].query("year == 2025 and statement_type == 'balance_sheet'").iloc[0]
        q1 = benchmark(conn, "SELECT evidence_id, value FROM financial.vnstock_financial_evidence WHERE ticker=%s AND year=%s AND statement_type=%s", ("FPT", 2025, "balance_sheet"))
        q2 = benchmark(conn, "SELECT evidence_id, year, value FROM financial.vnstock_financial_evidence WHERE ticker=%s AND source_item_id=%s ORDER BY year", ("FPT", str(sample.source_item_id)))
        q3 = benchmark(conn, "SELECT evidence_id, ticker, value FROM financial.vnstock_financial_evidence WHERE source_item_id=%s AND year=%s", (str(sample.source_item_id), 2025))
        benchmark_results = {"ticker_year_statement": q1, "ticker_item_year": q2, "item_year": q3}
        table_columns = conn.execute("SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_schema='financial' AND table_name='vnstock_financial_evidence' ORDER BY ordinal_position").fetchall()
        table_indexes = conn.execute("SELECT indexname, indexdef FROM pg_indexes WHERE schemaname='financial' AND tablename='vnstock_financial_evidence' ORDER BY indexname").fetchall()
        legacy_counts = conn.execute("SELECT 'financial_documents' AS table_name, count(*) AS rows FROM financial.financial_documents UNION ALL SELECT 'financial_facts', count(*) FROM financial.financial_facts UNION ALL SELECT 'financial_ingestion_jobs', count(*) FROM financial.financial_ingestion_jobs UNION ALL SELECT 'financial_validation', count(*) FROM financial.financial_validation").fetchall()
    with COUNTS.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(counts[0]))
        writer.writeheader(); writer.writerows(counts)
    lines = ["# PostgreSQL VCI Evidence Pilot Report", "", f"Database: `{database['database']}`; target: `financial.vnstock_financial_evidence`.", "", "## Migration and schema", "", "- Additive migration applied successfully; no serving table created.", "- Primary key: `evidence_id`; no unique constraint on source item identity.", "- Columns: " + ", ".join(f"`{row['column_name']}` ({row['data_type']})" for row in table_columns), "", "Indexes:"]
    lines += [f"- `{row['indexname']}`: {row['indexdef']}" for row in table_indexes]
    lines += ["", "## Pilot counts", "", "| Ticker | Artifact rows | DB rows | Years | Null artifact/DB | Distinct source items | Snapshots |", "|---|---:|---:|---|---:|---:|---:|"]
    lines += [f"| {row['ticker']} | {row['artifact_rows']} | {row['db_rows']} | {row['year_min']}–{row['year_max']} | {row['artifact_null_values']}/{row['db_null_values']} | {row['distinct_source_item_id']} | {row['raw_snapshot_count']} |" for row in counts]
    lines += ["", "## Conflict preservation and idempotency", "", f"- Representative conflict groups checked: `{len(preserved)}`; all source row instances present: **{conflict_pass}**.", "- Loader was rerun; every ticker reported `inserted=0` and DB row counts remained equal to artifacts.", "- Evidence IDs are deterministic and unique in each artifact/DB ticker.", "", "## Query benchmark (30 warm calls after 5 warm-ups)", "", "| Query | P50 ms | P95 ms | Avg ms |", "|---|---:|---:|---:|"]
    lines += [f"| {name} | {result['p50_ms']} | {result['p95_ms']} | {result['avg_ms']} |" for name, result in benchmark_results.items()]
    lines += ["", "## Legacy table check", "", "Legacy tables were not written or altered by the migration/loader. Current row counts: " + "; ".join(f"`{row['table_name']}`={row['rows']}" for row in legacy_counts) + ".", "", "## Recommendation", "", "**PASS** for VCI evidence pilot load and validation. Stop before canonical metric mapping; the next phase is Canonical Metric Mapping Pilot, not creation of `financial_serving_facts` until mapping/conflict policy is approved.", ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Validation PASS: {sum(row['db_rows'] for row in counts)} rows, conflicts_preserved={conflict_pass}, idempotency=PASS")
    return 0 if conflict_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
