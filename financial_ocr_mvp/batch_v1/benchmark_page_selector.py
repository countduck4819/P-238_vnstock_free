from __future__ import annotations
import json
import shutil
import tempfile
import time
from pathlib import Path
import fitz
from financial_ocr_mvp.batch_v1.minio_scanner import make_client
from financial_ocr_mvp.batch_v1.page_selector import select_pages

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "financial_ocr_mvp/output/batch_v1/page_selector_benchmark.json"
SAMPLES = [
    ("HPG", 2015, "annual", "financial-reports/consolidated/HPG/2015/annual/HPG_2015_audited_consolidated_2677f7e0.pdf"),
    ("HPG", 2015, "quarterly", "financial-reports/consolidated/HPG/2015/quarterly/HPG_Q1_2015_consolidated_3e838d2f.pdf"),
    ("VNM", 2015, "quarterly_native_text", "financial-reports/consolidated/VNM/2015/quarterly/VNM_Q1_2015_consolidated_07049c04.pdf"),
]

def main():
    client = make_client()
    reports = []
    with tempfile.TemporaryDirectory(prefix="p238_selector_benchmark_") as tmp:
        for ticker, year, report_type, source_path in SAMPLES:
            pdf = Path(tmp) / f"{ticker}_{report_type}.pdf"
            client.fget_object("stock-data", source_path, str(pdf))
            with fitz.open(pdf) as document:
                native_pages = sum(bool(page.get_text("text").strip()) for page in document)
            started = time.perf_counter()
            result = select_pages(pdf, use_ocr=False)
            seconds = round(time.perf_counter() - started, 3)
            reports.append({
                "ticker": ticker,
                "year": year,
                "report_type": report_type,
                "source_path": source_path,
                "selector_mode": result.get("selector_mode"),
                "native_text_pages": native_pages,
                "original_pages": result["original_pages"],
                "selected_pages": result["selected_pages"],
                "reduction_percent": result["reduction_percent"],
                "selector_seconds": seconds,
                "keep_pages": [
                    {"page": p["page"], "concept": p["active_section"], "reason": p["reason"]}
                    for p in result["pages"] if p["classification"] == "KEEP"
                ],
                "skip_pages": [
                    {"page": p["page"], "reason": p["reason"]}
                    for p in result["pages"] if p["classification"] == "SKIP"
                ],
                "uncertain_pages": result["uncertain_pages"],
                "detected_core_sections": sorted({m["concept"] for p in result["pages"] for m in p["matches"] if m["kind"] == "CORE"}),
                "detected_important_sections": sorted({m["concept"] for p in result["pages"] for m in p["matches"] if m["kind"] == "IMPORTANT"}),
                "missing_core_sections": result["missing_core_sections"],
                "navigation_status": result["navigation_status"],
            })
    output = {
        "schema": "page_selector_benchmark_v1",
        "policy": "read_only_minio_conservative",
        "pipeline_executed": False,
        "postgres_imported": False,
        "reports": reports,
        "conclusion": "PAGE_SELECTOR_READY" if all(r["navigation_status"] == "OK" and not r["missing_core_sections"] for r in reports) else "PAGE_SELECTOR_NOT_EFFECTIVE",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"conclusion": output["conclusion"], "reports": [
        {k: r[k] for k in ("ticker", "report_type", "source_path", "native_text_pages", "original_pages", "selected_pages", "reduction_percent", "selector_seconds", "uncertain_pages", "detected_core_sections", "missing_core_sections")}
        for r in reports]}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
