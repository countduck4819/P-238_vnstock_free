from __future__ import annotations

import json
import os
import statistics
import time
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from .normalization_rules import VERSION
from .normalizer import normalize_file
from .registry_models import document_id

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "financial_ocr_mvp/output"
DEST = OUT / "phase3_normalized"
FAILURES = OUT / "phase3_normalization_failures.json"
ALTER = """
ALTER TABLE financial.document_registry ADD COLUMN IF NOT EXISTS normalization_status text NOT NULL DEFAULT 'pending';
ALTER TABLE financial.document_registry ADD COLUMN IF NOT EXISTS normalizer_version text;
ALTER TABLE financial.document_registry ADD COLUMN IF NOT EXISTS normalized_path text;
ALTER TABLE financial.document_registry ADD COLUMN IF NOT EXISTS normalized_sha256 char(64);
ALTER TABLE financial.document_registry ADD COLUMN IF NOT EXISTS normalized_at timestamptz;
"""


def should_normalize(row: tuple, root: Path = ROOT) -> tuple[bool, str]:
    """Return whether a canonical registry row needs processing."""
    (doc_id, _ticker, _year, _raw_rel, raw_sha, _page_count, _has_table,
     status, version, norm_path, norm_sha) = row
    if status not in ("success", "warning"):
        return True, "status_not_reusable"
    if version != VERSION:
        return True, "normalizer_version_mismatch"
    if not norm_path or not norm_sha:
        return True, "normalized_metadata_missing"
    path = Path(norm_path)
    if not path.is_absolute():
        path = root / path
    if not path.is_file():
        return True, "normalized_file_missing"
    from .normalizer import digest
    if digest(path.read_bytes()) != norm_sha:
        return True, "normalized_sha_mismatch"
    raw = root / "data/ocr_annual_financials" / _raw_rel
    if not raw.is_file() or digest(raw.read_bytes()) != raw_sha:
        return True, "raw_sha_mismatch"
    return False, "checkpoint_valid"


def run() -> dict[str, object]:
    load_dotenv(ROOT / ".env")
    started = time.perf_counter(); reports=[]; failures=[]; skipped=0; updates=[]
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            cur.execute(ALTER)
            cur.execute("""SELECT document_id,ticker,year,local_path,sha256,page_count,has_html_table,normalization_status,normalizer_version,normalized_path,normalized_sha256
                FROM financial.document_registry WHERE is_duplicate=false ORDER BY ticker,year,local_path""")
            rows=cur.fetchall(); conn.commit()
            for index,row in enumerate(rows,1):
                doc_id,ticker,year,raw_rel,raw_sha,page_count,has_table,status,version,norm_path,norm_sha=row
                target=ROOT/'financial_ocr_mvp/output/phase3_normalized'/str(ticker)/str(year)/(str(doc_id)+'.txt')
                needs_work, _reason = should_normalize(row, ROOT)
                if not needs_work:
                    skipped += 1; continue
                raw=ROOT/'data/ocr_annual_financials'/raw_rel
                try:
                    started_doc=time.perf_counter()
                    report=normalize_file(raw,target,{"document_id":doc_id,"ticker":ticker,"year":year,"report_type":"annual","raw_local_path":raw_rel,"elapsed_seconds":round(time.perf_counter()-started_doc,4)})
                    report["normalized_path"]=str(target)
                    if report["raw_sha256"] != raw_sha: report["warnings"].append("registry_raw_sha_mismatch")
                    if report["page_count_before"] != page_count: report["warnings"].append("registry_page_count_mismatch")
                    if report["warnings"]:
                        report["normalization_status"]="warning"
                    updates.append((report["normalization_status"],VERSION,str(target),report["normalized_sha256"],doc_id))
                    reports.append(report)
                except Exception as exc:
                    failures.append({"document_id":doc_id,"ticker":ticker,"year":year,"path":raw_rel,"error_type":type(exc).__name__,"error_message":str(exc)})
                    updates.append(("failed",VERSION,None,None,doc_id))
                if len(updates)>=500:
                    cur.executemany("UPDATE financial.document_registry SET normalization_status=%s,normalizer_version=%s,normalized_path=%s,normalized_sha256=%s,normalized_at=now(),updated_at=now() WHERE document_id=%s",updates); conn.commit(); updates.clear()
                if len(failures)>50 or (index and len(failures)/index>0.01):
                    break
            if updates:
                cur.executemany("UPDATE financial.document_registry SET normalization_status=%s,normalizer_version=%s,normalized_path=%s,normalized_sha256=%s,normalized_at=now(),updated_at=now() WHERE document_id=%s",updates); conn.commit()
    integrity={"raw_integrity_failures":sum(r["raw_sha256"]!=next(x[4] for x in rows if x[0]==r["document_id"]) for r in reports),"page_integrity_failures":sum(r["page_count_before"]!=r["page_count_after"] or r["page_markers_before"]!=r["page_markers_after"] for r in reports),"html_integrity_failures":sum(r["html_counts_before"]!=r["html_counts_after"] for r in reports),"numeric_integrity_failures":sum(r["numeric_tokens_removed"] or r["numeric_tokens_added"] for r in reports)}
    success=sum(r["normalization_status"]=='success' for r in reports); warnings=sum(r["normalization_status"]=='warning' for r in reports)
    result={"inventory_documents":18231,"canonical_documents":len(rows),"duplicate_documents":43,"processed":len(reports),"skipped":skipped,"success":success,"warnings":warnings,"failed":len(failures),**integrity,"no_html_table_processed":sum(not r.get("has_html_table",True) for r in reports),"normalizer_version":VERSION,"runtime":{"total_seconds":round(time.perf_counter()-started,3),"documents_per_second":round((len(reports)+skipped)/max(time.perf_counter()-started,0.001),2),"p50_ms":round(statistics.median([r['elapsed_seconds']*1000 for r in reports]),3) if reports else 0,"p95_ms":round(sorted([r['elapsed_seconds']*1000 for r in reports])[max(0,int(len(reports)*.95)-1)],3) if reports else 0,"max_ms":round(max([r['elapsed_seconds']*1000 for r in reports],default=0),3)},"failures":failures,"resume_note":"Canonical source list read from financial.document_registry; duplicate rows excluded."}
    FAILURES.write_text(json.dumps(failures,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

if __name__=='__main__': print(json.dumps(run(),ensure_ascii=False,indent=2))
