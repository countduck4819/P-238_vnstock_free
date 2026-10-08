"""Read-only MinIO scanner for the first batch-v1 dry-run."""
from __future__ import annotations

from typing import Any, Iterable

from minio import Minio

from .config import BUCKET, PREFIX, TICKERS, YEAR, minio_settings
from .path_parser import parse_source_path


def make_client() -> Minio:
    settings = minio_settings()
    return Minio(
        str(settings["endpoint"]),
        access_key=str(settings["access_key"]),
        secret_key=str(settings["secret_key"]),
        secure=bool(settings["secure"]),
    )


def scan(
    client: Minio,
    bucket: str = BUCKET,
    prefix: str = PREFIX,
    tickers: Iterable[str] = TICKERS,
    year: int = YEAR,
) -> dict[str, Any]:
    allowed = {ticker.upper() for ticker in tickers}
    records: list[dict[str, Any]] = []
    ignored: list[dict[str, str]] = []
    for obj in client.list_objects(bucket, prefix=prefix, recursive=True):
        path = obj.object_name
        parsed = parse_source_path(path)
        if not path.lower().endswith(".pdf"):
            ignored.append({"source_path": path, "reason": "not_pdf"})
            continue
        if parsed is None:
            ignored.append({"source_path": path, "reason": "unsupported_path_layout"})
            continue
        if parsed["ticker"] not in allowed:
            ignored.append({"source_path": path, "reason": "ticker_not_selected"})
            continue
        if parsed["year"] != year:
            ignored.append({"source_path": path, "reason": "year_not_selected"})
            continue
        records.append(parsed)
    records.sort(key=lambda item: (item["ticker"], item["report_type"], item["quarter"] or 0, item["source_path"]))
    return {
        "bucket": bucket,
        "prefix": prefix,
        "selected_tickers": sorted(allowed),
        "selected_year": year,
        "pdf_count": len(records),
        "records": records,
        "ignored_count": len(ignored),
        "ignored": ignored,
    }
