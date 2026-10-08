"""Process explicitly selected ingestion jobs; never choose a random job."""
from __future__ import annotations

import argparse
import json
import os
from typing import Any

import psycopg
from dotenv import load_dotenv

from .config import ROOT
from .pipeline_adapter import PipelineAdapter, update_job

load_dotenv(ROOT / ".env")
MAX_RETRIES = 3


def ensure_needs_review_status(conn: psycopg.Connection) -> None:
    conn.execute("ALTER TABLE financial.financial_ingestion_jobs DROP CONSTRAINT IF EXISTS financial_ingestion_jobs_status_check")
    conn.execute("""ALTER TABLE financial.financial_ingestion_jobs ADD CONSTRAINT financial_ingestion_jobs_status_check
        CHECK (status IN ('pending','processing','completed','needs_review','failed','retry'))""")
    conn.commit()


def claim(conn: psycopg.Connection, args: argparse.Namespace) -> dict[str, Any] | None:
    filters = ["status IN ('pending','retry')", "retry_count < %s"]
    params: list[Any] = [MAX_RETRIES]
    for field, value in (("ticker", args.ticker), ("year", args.year), ("quarter", args.quarter), ("report_type", args.report_type)):
        if value is not None:
            filters.append(f"{field}=%s")
            params.append(value)
    with conn.transaction():
        row = conn.execute(f"""SELECT id,ticker,year,quarter,report_type,source_path,retry_count
            FROM financial.financial_ingestion_jobs WHERE {' AND '.join(filters)}
            ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1""", params).fetchone()
        if row is None:
            return None
        conn.execute("UPDATE financial.financial_ingestion_jobs SET status='processing',started_at=now(),updated_at=now() WHERE id=%s", (row[0],))
    return dict(zip(("id","ticker","year","quarter","report_type","source_path","retry_count"), row))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run selected financial ingestion jobs")
    parser.add_argument("--ticker")
    parser.add_argument("--year", type=int)
    parser.add_argument("--quarter", type=int)
    parser.add_argument("--report-type", choices=("quarterly", "annual"))
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if not args.once:
        parser.error("bắt buộc --once trong batch_v1 test để tránh chạy cả queue")
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        ensure_needs_review_status(conn)
        job = claim(conn, args)
        if job is None:
            raise SystemExit("Không tìm thấy job phù hợp")
        try:
            result = PipelineAdapter().process(job)
            status = "needs_review" if result.get("status") == "completed" and result.get("canonical_status") == "needs_review" else result.get("status", "failed")
            update_job(conn, int(job["id"]), status, result)
        except Exception as exc:
            result = {"status": "failed", "error": str(exc), "failed_stage": "adapter"}
            next_status = "failed" if int(job["retry_count"]) + 1 >= MAX_RETRIES else "retry"
            update_job(conn, int(job["id"]), next_status, result)
        print(json.dumps({"job": job, "result": result}, ensure_ascii=False, indent=2, default=str))
        if result.get("status") == "failed":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
