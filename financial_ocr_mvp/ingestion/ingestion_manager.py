"""Scan MinIO PDFs and idempotently create financial ingestion jobs.

This module only creates queue records. It does not run OCR or modify financial
documents/facts.
"""
from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

import psycopg
from dotenv import load_dotenv

try:
    from minio import Minio
except ImportError:  # pragma: no cover - exercised when optional dependency is absent
    Minio = None

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
PERIOD_RE = re.compile(r"^(?P<year>\d{4})/(?P<period>Q[1-4]|YEAR|ANNUAL)/(?P<file>.+\.pdf)$", re.I)


def parse_object_path(path: str) -> dict[str, object] | None:
    """Parse ``TICKER/YYYY/Q1/file.pdf`` without inferring missing metadata."""
    parts = path.strip("/").split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1].lower().endswith(".pdf"):
        return None
    match = PERIOD_RE.match(parts[1])
    if not match:
        return None
    period = match.group("period").upper()
    quarter = int(period[1]) if period.startswith("Q") else None
    return {
        "ticker": parts[0].upper(),
        "year": int(match.group("year")),
        "quarter": quarter,
        "report_type": "quarterly" if quarter else "annual",
        "source_path": path.strip("/"),
    }


def minio_client() -> tuple[object, str]:
    if Minio is None:
        raise RuntimeError("MinIO SDK chưa cài. Cài dependency: pip install minio")
    endpoint = os.getenv("MINIO_ENDPOINT")
    access_key = os.getenv("MINIO_ACCESS_KEY")
    secret_key = os.getenv("MINIO_SECRET_KEY")
    if not endpoint or not access_key or not secret_key:
        raise RuntimeError("Thiếu MINIO_ENDPOINT, MINIO_ACCESS_KEY hoặc MINIO_SECRET_KEY")
    secure = os.getenv("MINIO_SECURE", "false").lower() in {"1", "true", "yes"}
    return Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure), os.getenv(
        "MINIO_BUCKET", "financial-reports"
    )


def scan(bucket: str | None = None, prefix: str = "", dry_run: bool = False) -> dict[str, int]:
    client, default_bucket = minio_client()
    bucket = bucket or default_bucket
    objects = client.list_objects(bucket, prefix=prefix, recursive=True)
    discovered = inserted = skipped = invalid = 0
    connection = None if dry_run else psycopg.connect(os.environ["DATABASE_URL"])
    try:
        for obj in objects:
            path = obj.object_name
            if not path.lower().endswith(".pdf"):
                continue
            discovered += 1
            metadata = parse_object_path(path)
            if metadata is None:
                invalid += 1
                print(f"SKIP invalid path: {path}")
                continue
            if dry_run:
                print(f"WOULD INSERT {metadata}")
                inserted += 1
                continue
            with connection.cursor() as cur:
                cur.execute(
                    """INSERT INTO financial.financial_ingestion_jobs
                    (ticker, year, quarter, report_type, source_path)
                    VALUES (%(ticker)s, %(year)s, %(quarter)s, %(report_type)s, %(source_path)s)
                    ON CONFLICT (source_path) DO NOTHING""",
                    metadata,
                )
                if cur.rowcount:
                    inserted += 1
                else:
                    skipped += 1
        if connection:
            connection.commit()
    finally:
        if connection:
            connection.close()
    return {"discovered": discovered, "inserted": inserted, "skipped": skipped, "invalid": invalid}


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan MinIO PDFs into financial ingestion jobs")
    parser.add_argument("--bucket")
    parser.add_argument("--prefix", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(scan(args.bucket, args.prefix, args.dry_run))


if __name__ == "__main__":
    main()
