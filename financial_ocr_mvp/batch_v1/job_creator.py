"""Create idempotent PostgreSQL jobs from an approved batch-v1 dry-run report.

This module writes only queue rows. It never writes to MinIO and never invokes
the OCR pipeline.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def create_jobs(report_path: Path) -> dict[str, int]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    records = report.get("records", [])
    inserted = skipped = 0
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        for record in records:
            cur = conn.execute(
                """INSERT INTO financial.financial_ingestion_jobs
                (ticker, year, quarter, report_type, source_path)
                VALUES (%(ticker)s, %(year)s, %(quarter)s, %(report_type)s, %(source_path)s)
                ON CONFLICT (source_path) DO NOTHING""",
                record,
            )
            if cur.rowcount:
                inserted += 1
            else:
                skipped += 1
        conn.commit()
    return {"report_records": len(records), "inserted": inserted, "skipped_existing": skipped}


def main() -> None:
    parser = argparse.ArgumentParser(description="Create ingestion jobs from batch-v1 dry-run report")
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    print(json.dumps(create_jobs(args.report), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
