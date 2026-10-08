from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import fitz

from .core_statement_locator import locate
from .minio_scanner import make_client

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "financial_ocr_mvp/output/batch_v1/core_locator_benchmark.json"
SAMPLES = [
    ("HPG", 2015, "annual", "financial-reports/consolidated/HPG/2015/annual/HPG_2015_audited_consolidated_2677f7e0.pdf"),
    ("HPG", 2015, "quarterly", "financial-reports/consolidated/HPG/2015/quarterly/HPG_Q1_2015_consolidated_3e838d2f.pdf"),
    ("VNM", 2015, "quarterly_native_text", "financial-reports/consolidated/VNM/2015/quarterly/VNM_Q1_2015_consolidated_07049c04.pdf"),
]


def main() -> None:
    client = make_client()
    reports = []
    with tempfile.TemporaryDirectory(prefix="p238_core_locator_") as tmp:
        for ticker, year, report_type, source_path in SAMPLES:
            pdf = Path(tmp) / f"{ticker}_{report_type}.pdf"
            client.fget_object("stock-data", source_path, str(pdf))
            with fitz.open(pdf) as document:
                native_pages = sum(bool(page.get_text("text").strip()) for page in document)
            result = locate(pdf)
            reports.append({
                "ticker": ticker,
                "year": year,
                "report_type": report_type,
                "source_path": source_path,
                "native_text_pages": native_pages,
                "total_pages": result["total_pages"],
                "searched_pages": result["searched_pages"],
                "locator_seconds": result["locator_seconds"],
                "early_stop": result["early_stop"],
                "sections": result["sections"],
                "selected_pages": result["selected_pages"],
                "missing_sections": result["missing_sections"],
                "navigation_status": result["navigation_status"],
            })
    ready = all(
        not report["missing_sections"]
        and report["early_stop"]
        and report["searched_pages"] < report["total_pages"]
        for report in reports
    )
    output = {
        "schema": "core_locator_benchmark_v1",
        "policy": "read_only_minio_no_pipeline",
        "pipeline_executed": False,
        "postgres_imported": False,
        "reports": reports,
        "conclusion": "CORE_LOCATOR_READY" if ready else "CORE_LOCATOR_NOT_EFFECTIVE",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "conclusion": output["conclusion"],
        "reports": [
            {key: report[key] for key in (
                "ticker", "report_type", "source_path", "native_text_pages",
                "total_pages", "searched_pages", "locator_seconds",
                "early_stop", "sections", "selected_pages",
                "missing_sections", "navigation_status",
            )}
            for report in reports
        ],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
