from __future__ import annotations

import csv
import json
import os
import re
import time
from collections import defaultdict
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from .registry_models import document_id, sha256

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "financial_ocr_mvp/output/dataset_inventory.json"
OUT = ROOT / "financial_ocr_mvp/output"
DDL = """
CREATE TABLE IF NOT EXISTS financial.document_registry (
 document_id text PRIMARY KEY, ticker text NOT NULL, year integer NOT NULL,
 report_type text NOT NULL DEFAULT 'annual', company_type text NULL,
 local_path text NOT NULL UNIQUE, file_name text NOT NULL, file_size bigint NOT NULL,
 sha256 char(64) NOT NULL, page_count integer NULL, has_html_table boolean NOT NULL,
 has_page_marker boolean NOT NULL, is_duplicate boolean NOT NULL DEFAULT false,
 duplicate_of_document_id text NULL REFERENCES financial.document_registry(document_id),
 parse_status text NOT NULL DEFAULT 'pending', validation_status text NOT NULL DEFAULT 'not_started',
 ingestion_status text NOT NULL DEFAULT 'registered', parser_version text NULL,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS document_registry_ticker_year_report_idx ON financial.document_registry(ticker, year, report_type);
CREATE INDEX IF NOT EXISTS document_registry_sha256_idx ON financial.document_registry(sha256);
CREATE TABLE IF NOT EXISTS financial.data_coverage (
 ticker text NOT NULL, year integer NOT NULL, report_type text NOT NULL,
 document_available boolean NOT NULL, canonical_document_id text NULL REFERENCES financial.document_registry(document_id),
 document_count integer NOT NULL, duplicate_count integer NOT NULL, has_html_table boolean NOT NULL,
 coverage_status text NOT NULL, updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (ticker, year, report_type)
);
CREATE INDEX IF NOT EXISTS data_coverage_ticker_year_report_idx ON financial.data_coverage(ticker, year, report_type);
"""


def register() -> dict[str, object]:
    load_dotenv(ROOT / ".env")
    payload = json.loads(INVENTORY.read_text(encoding="utf-8"))
    rows = payload["reports"]
    by_hash = defaultdict(list)
    for row in rows: by_hash[row["sha256"]].append(row)
    canonical = {h: sorted(group, key=lambda r: r["path"])[0] for h, group in by_hash.items()}
    started = time.perf_counter()
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            cur.execute(DDL)
            registry_rows = []
            for row in rows:
                path = row["path"]; doc_id = document_id(path); is_dup = path != canonical[row["sha256"]]["path"]
                canonical_id = document_id(canonical[row["sha256"]]["path"]) if is_dup else None
                registry_rows.append((doc_id,row["ticker"],row["year"],path,Path(path).name,row["file_size"],row["sha256"],row["page_count"],row["has_table"],row["page_count"] is not None,is_dup,canonical_id))
            cur.executemany("""INSERT INTO financial.document_registry
                    (document_id,ticker,year,report_type,local_path,file_name,file_size,sha256,page_count,has_html_table,has_page_marker,is_duplicate,duplicate_of_document_id,parser_version)
                    VALUES (%s,%s,%s,'annual',%s,%s,%s,%s,%s,%s,%s,%s,%s,'inventory_v1')
                    ON CONFLICT (document_id) DO UPDATE SET updated_at=now(), is_duplicate=EXCLUDED.is_duplicate, duplicate_of_document_id=EXCLUDED.duplicate_of_document_id""",
                    registry_rows)
            cur.execute("""INSERT INTO financial.data_coverage
                SELECT ticker,year,report_type,true,(array_agg(document_id ORDER BY is_duplicate, local_path))[1],count(*),count(*) FILTER (WHERE is_duplicate),bool_or(has_html_table),'available',now()
                FROM financial.document_registry GROUP BY ticker,year,report_type
                ON CONFLICT (ticker,year,report_type) DO UPDATE SET document_available=EXCLUDED.document_available, canonical_document_id=EXCLUDED.canonical_document_id, document_count=EXCLUDED.document_count, duplicate_count=EXCLUDED.duplicate_count, has_html_table=EXCLUDED.has_html_table, coverage_status=EXCLUDED.coverage_status, updated_at=now()""")
            conn.commit()
    duplicate_report={h:{"sha256":h,"canonical_document":canonical[h]["path"],"duplicate_documents":[r["path"] for r in group if r["path"] != canonical[h]["path"]]} for h,group in by_hash.items() if len(group)>1}
    result={"inventory_total":len(rows),"registry_total":len(rows),"canonical_documents":len(rows)-sum(len(v["duplicate_documents"]) for v in duplicate_report.values()),"duplicate_documents":sum(len(v["duplicate_documents"]) for v in duplicate_report.values()),"duplicate_groups":len(duplicate_report),"elapsed_seconds":round(time.perf_counter()-started,3)}
    (OUT/"duplicate_registry_report.json").write_text(json.dumps(duplicate_report,ensure_ascii=False,indent=2),encoding="utf-8")
    return result


if __name__ == "__main__": print(json.dumps(register(),ensure_ascii=False,indent=2))
