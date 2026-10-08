from __future__ import annotations

import json
import statistics
import time
from pathlib import Path
import os
import psycopg
from dotenv import load_dotenv

from .page_parser import split_pages
from .section_parser import parse_sections, normalize
from .section_taxonomy import CORE
from .document_resolution import resolve_normalized_document

ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/"financial_ocr_mvp/output"; INV=OUT/"dataset_inventory.json"; REG=OUT/"duplicate_registry_report.json"; DEST=OUT/"phase4_section_parser_samples"

def choose(rows):
    dup=json.loads(REG.read_text())
    excluded={p for x in dup.values() for p in x["duplicate_documents"]}
    rows=[r for r in rows if r["path"] not in excluded]
    by_size=sorted(rows,key=lambda r:int(r["file_size"]))
    no=[r for r in rows if not r["has_table"]]; yes=[r for r in rows if r["has_table"]]
    picks=no[:8]+yes[:22]+by_size[:10]+by_size[-10:]
    seen=set(); result=[]
    for r in picks:
        if r["path"] not in seen: seen.add(r["path"]); result.append(r)
    return result[:50]

def independent_expected(text):
    value=normalize(text)
    expected=[]
    for kind,terms in {"balance_sheet":("bang can doi ke toan","tinh hinh tai chinh"),"income_statement":("ket qua hoat dong kinh doanh","ket qua kinh doanh"),"cash_flow":("luu chuyen tien te",),"notes":("thuyet minh bao cao tai chinh",),"audit_report":("bao cao kiem toan doc lap","y kien kiem toan")}.items():
        pages=[]
        for block in text.split("===== PAGE "):
            if any(t in normalize(block) for t in terms):
                try: pages.append(int(block.split("=====")[0].strip()))
                except (ValueError,IndexError): pass
        if pages: expected.append({"type":kind,"pages":pages})
    return expected

def main():
    load_dotenv(ROOT / ".env")
    rows=choose(json.loads(INV.read_text())["reports"])
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn, conn.cursor() as cur:
        cur.execute("SELECT document_id,local_path FROM financial.document_registry WHERE is_duplicate=false")
        by_path={path: str(doc_id) for doc_id,path in cur.fetchall()}
    rows=[{**row,"document_id":by_path[row["path"]]} for row in rows if row["path"] in by_path]
    results=[]; start=time.perf_counter()
    for row in rows:
        try: resolved, path = resolve_normalized_document(str(row["document_id"]))
        except Exception as exc:
            results.append({"ticker":row["ticker"],"year":row["year"],"document_id":row["document_id"],"page_integrity":False,"resolution_error":str(exc)}); continue
        text=path.read_text(encoding="utf-8",errors="replace"); t=time.perf_counter(); pages=split_pages(text); sections=parse_sections(pages); expected=independent_expected(text)
        results.append({"ticker":row["ticker"],"year":row["year"],"document_id":str(resolved["document_id"]),"normalized_path":str(path),"normalized_sha256":resolved["normalized_sha256"],"expected_pages":len([x for x in text.split('===== PAGE ') if '=====' in x]),"parsed_pages":len(pages),"page_integrity":len(pages)==row["page_count"],"expected_core":expected,"detected_core":[s for s in sections if s["type"] in CORE],"sections":sections,"elapsed_seconds":round(time.perf_counter()-t,4),"company_type":"unknown"})
        (DEST/str(row["ticker"])/str(row["year"])).mkdir(parents=True,exist_ok=True); (DEST/str(row["ticker"])/str(row["year"])/(str(resolved["document_id"])+'.json')).write_text(json.dumps(results[-1],ensure_ascii=False,indent=2))
    core_expected=sum(bool(r["expected_core"]) for r in results); core_detected=sum(bool(r["detected_core"]) for r in results); summary={"documents_tested":len(results),"pages_tested":sum(r["parsed_pages"] for r in results),"core_detection":{"expected_documents":core_expected,"detected_documents":core_detected},"page_integrity_pass":all(r["page_integrity"] for r in results),"runtime":{"total_seconds":round(time.perf_counter()-start,3),"documents_per_second":round(len(results)/max(time.perf_counter()-start,.001),2),"p50_document_ms":round(statistics.median([r["elapsed_seconds"]*1000 for r in results]),3),"p95_document_ms":round(sorted([r["elapsed_seconds"]*1000 for r in results])[max(0,int(len(results)*.95)-1)],3)},"parser_version":"section_parser_v1","ground_truth_note":"Expected labels are independent broad alias scan artifacts; manual review required before production."}; conclusion="PHASE_4_PILOT_READY" if results and summary["page_integrity_pass"] else "PHASE_4_PILOT_NEEDS_FIX"; output={"schema":"phase4_section_parser_pilot_v1","summary":summary,"documents":results,"conclusion":conclusion}; (OUT/"phase4_section_parser_pilot.json").write_text(json.dumps(output,ensure_ascii=False,indent=2)); (OUT/"phase4_section_parser_failures.json").write_text(json.dumps([r for r in results if not r["page_integrity"]],ensure_ascii=False,indent=2)); (OUT/"phase4_section_parser_pilot.md").write_text(f"# Phase 4 Section Parser Pilot\n\n- Documents: {len(results)}\n- Pages: {summary['pages_tested']}\n- Page integrity: {summary['page_integrity_pass']}\n- Ground truth: independent broad alias scan; manual review required\n- Conclusion: **{conclusion}**\n")
    print(json.dumps({"summary":summary,"conclusion":conclusion},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
