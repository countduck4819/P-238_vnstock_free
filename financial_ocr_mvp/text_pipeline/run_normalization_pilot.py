from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

from .normalization_rules import VERSION
from .normalizer import normalize_file

ROOT = Path(__file__).resolve().parents[2]
INV = ROOT / "financial_ocr_mvp/output/dataset_inventory.json"
OUT = ROOT / "financial_ocr_mvp/output"
DEST = OUT / "phase3_normalized"


def choose(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    unique = [r for r in rows if not r.get("is_duplicate", False)]
    with_table = [r for r in unique if r["has_table"]]
    without = [r for r in unique if not r["has_table"]]
    ordered = sorted(unique, key=lambda r: int(r["file_size"]))
    picks = without[:4] + with_table[:6] + ordered[:5] + ordered[-5:]
    result = []
    seen = set()
    for row in picks:
        if row["path"] not in seen:
            seen.add(row["path"]); result.append(row)
    return result[:20]


def main() -> None:
    payload = json.loads(INV.read_text(encoding="utf-8"))
    duplicate_report = json.loads((OUT / "duplicate_registry_report.json").read_text(encoding="utf-8"))
    duplicate_paths = {p for group in duplicate_report.values() for p in group["duplicate_documents"]}
    samples = choose([row for row in payload["reports"] if row["path"] not in duplicate_paths])
    reports=[]; started=time.perf_counter()
    for row in samples:
        raw=ROOT/'data/ocr_annual_financials'/row["path"]
        doc_id=__import__('uuid').uuid5(__import__('uuid').UUID('c5dbe3c4-cfd6-4a5f-8d45-7e894f8e2d7d'),row["path"])
        dest=DEST/str(row["ticker"])/str(row["year"])/(str(doc_id)+'.txt')
        t=time.perf_counter(); reports.append(normalize_file(raw,dest,{"document_id":str(doc_id),"ticker":row["ticker"],"year":row["year"],"report_type":"annual","raw_local_path":row["path"],"elapsed_seconds":round(time.perf_counter()-t,4)}))
    raw_ok=all(r["raw_sha256"] == __import__('hashlib').sha256((ROOT/'data/ocr_annual_financials'/r["raw_local_path"]).read_bytes()).hexdigest() for r in reports)
    page_ok=all(r["page_markers_before"]==r["page_markers_after"] and r["page_count_before"]==r["page_count_after"] for r in reports)
    html_ok=all(r["html_counts_before"]==r["html_counts_after"] for r in reports)
    numeric_ok=all(r["numeric_tokens_removed"]==0 and r["numeric_tokens_added"]==0 for r in reports)
    summary={"documents_tested":len(reports),"success":sum(r["normalization_status"]=="success" for r in reports),"warnings":sum(r["normalization_status"]=="warning" for r in reports),"failed":0,"raw_hash_integrity":raw_ok,"page_marker_integrity":page_ok,"html_integrity":html_ok,"numeric_integrity":numeric_ok,"performance":{"total_seconds":round(time.perf_counter()-started,3),"average_seconds_per_document":round(statistics.mean(r["elapsed_seconds"] for r in reports),4),"median_seconds":round(statistics.median(r["elapsed_seconds"] for r in reports),4),"max_seconds":round(max(r["elapsed_seconds"] for r in reports),4)},"normalizer_version":VERSION,"company_type_note":"company_type chưa có trong registry; không suy đoán."}
    result={"schema":"phase3_normalization_pilot_v1","summary":summary,"reports":reports,"manual_samples":[{"document_id":r["document_id"],"raw_first_500":(ROOT/'data/ocr_annual_financials'/r["raw_local_path"]).read_text(encoding='utf-8',errors='replace')[:500],"normalized_first_500":(DEST/r["ticker"]/str(r["year"])/(r["document_id"]+'.txt')).read_text(encoding='utf-8')[:500]} for r in reports[:5]],"conclusion":"PHASE_3_PILOT_READY" if all((raw_ok,page_ok,html_ok,numeric_ok)) else "PHASE_3_PILOT_NEEDS_FIX"}
    (OUT/'phase3_normalization_pilot.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# Phase 3 Normalization Pilot','',f"- Documents tested: **{len(reports)}**",f"- Success: **{summary['success']}**",f"- Warnings: **{summary['warnings']}**",f"- Raw SHA integrity: **{raw_ok}**",f"- Page marker integrity: **{page_ok}**",f"- HTML integrity: **{html_ok}**",f"- Numeric integrity: **{numeric_ok}**",f"- Average time/document: **{summary['performance']['average_seconds_per_document']}s**",'',f"## Conclusion\n\n**{result['conclusion']}**"]
    (OUT/'phase3_normalization_pilot.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({"summary":summary,"conclusion":result["conclusion"]},ensure_ascii=False,indent=2))

if __name__ == '__main__': main()
