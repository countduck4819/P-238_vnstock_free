from __future__ import annotations

import hashlib
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]


def resolve_normalized_document(document_id: str) -> tuple[dict[str, object], Path]:
    load_dotenv(ROOT / ".env")
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn, conn.cursor() as cur:
        cur.execute("""SELECT document_id,ticker,year,normalized_path,normalized_sha256
            FROM financial.document_registry WHERE document_id=%s AND is_duplicate=false""", (document_id,))
        row = cur.fetchone()
    if not row:
        raise FileNotFoundError(f"DOCUMENT_NOT_RESOLVED: {document_id}")
    did, ticker, year, normalized_path, expected_sha = row
    path = Path(normalized_path) if normalized_path else Path()
    if not path.is_absolute(): path = ROOT / path
    if not path.is_file(): raise FileNotFoundError(f"DOCUMENT_NOT_RESOLVED: missing {path}")
    actual_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual_sha != expected_sha: raise ValueError(f"DOCUMENT_NOT_RESOLVED: SHA mismatch for {did}")
    return {"document_id": str(did), "ticker": ticker, "year": year, "normalized_path": str(path), "normalized_sha256": expected_sha}, path
