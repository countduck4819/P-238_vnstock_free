"""Generic, isolated orchestration of the existing Financial OCR baseline."""
from __future__ import annotations

import argparse
import json
import resource
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DOC_PIPELINE = ROOT / "financial_ocr_mvp" / "docling_pipeline"
if str(DOC_PIPELINE) not in sys.path:
    sys.path.insert(0, str(DOC_PIPELINE))

import fitz
from docling.document_converter import DocumentConverter

from financial_ocr_mvp.docling_pipeline.extract_tables import extract_tables
from financial_ocr_mvp.docling_pipeline.semantic_mapper import map_table


CELL_RETRY = ROOT / "financial_ocr_mvp/docling_pipeline/cell_retry_rapidocr.py"
CELL_RETRY_V2 = ROOT / "financial_ocr_mvp/docling_pipeline/cell_retry_rapidocr_v2.py"
MERGE = ROOT / "financial_ocr_mvp/docling_pipeline/merge_rapidocr_candidates.py"
CONSISTENCY = ROOT / "financial_ocr_mvp/docling_pipeline/financial_consistency_check_v3.py"
FACT_BUILDER = ROOT / "financial_ocr_mvp/docling_pipeline/financial_fact_builder.py"
SEMANTIC = ROOT / "financial_ocr_mvp/docling_pipeline/financial_semantic_mapper.py"
RULES = ROOT / "financial_ocr_mvp/docling_pipeline/financial_rules_engine.py"
CANONICAL = ROOT / "financial_ocr_mvp/docling_pipeline/canonical_financial_builder.py"
IMPORTER = ROOT / "financial_ocr_mvp/database/import_canonical_to_postgres.py"


def run_stage(name: str, command: list[str]) -> float:
    started = time.perf_counter()
    try:
        subprocess.run(command, cwd=ROOT, check=True)
    except Exception as exc:
        raise RuntimeError(f"{name}: {exc}") from exc
    return round(time.perf_counter() - started, 3)


def peak_ram_mb() -> float | None:
    values = [resource.getrusage(resource.RUSAGE_SELF).ru_maxrss]
    try:
        values.append(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)
    except (AttributeError, ValueError):
        pass
    return round(max(values) / 1024, 2) if values else None


def render_pages(pdf: Path, directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    images: list[Path] = []
    with fitz.open(pdf) as document:
        for index, page in enumerate(document):
            path = directory / f"page_{index + 1:04d}.png"
            page.get_pixmap(dpi=400, alpha=False).save(path)
            images.append(path)
    return images


def extract_page_tables(images: list[Path], raw_dir: Path, pdf: Path) -> tuple[dict[str, Any], list[tuple[int, Path]]]:
    """Run Docling once for the PDF, then associate tables with rendered pages."""
    exported = DocumentConverter().convert(str(pdf)).document.export_to_dict()
    exported.setdefault("origin", {})["filename"] = str(pdf)
    docling_path = raw_dir / "document_docling.json"
    docling_path.write_text(json.dumps(exported, ensure_ascii=False, indent=2), encoding="utf-8")
    extracted = extract_tables(exported)
    all_tables: list[dict[str, Any]] = []
    table_images: list[tuple[int, Path]] = []
    for table in extracted["tables"]:
        page_number = int(table.get("source", {}).get("page") or 1)
        table["source"]["page"] = page_number
        table["source"]["pdf"] = str(pdf)
        for row in table.get("cell_sources", []):
            for source in row:
                if source:
                    source["page"] = page_number
        all_tables.append(table)
        if 1 <= page_number <= len(images):
            table_images.append((page_number, images[page_number - 1]))
    grid = {"schema": "financial_raw_grid_v1", "source": {"pdf": str(pdf), "method": "Docling"}, "tables": all_tables}
    (raw_dir / "raw_grid.json").write_text(json.dumps(grid, ensure_ascii=False, indent=2), encoding="utf-8")
    return grid, table_images


def build_mapping(grid: dict[str, Any], pdf: Path, ticker: str, year: int, quarter: int | None) -> dict[str, Any]:
    mapped: list[dict[str, Any]] = []
    for table in grid.get("tables", []):
        rows = table.get("rows", [])
        malformed = any(len(row) < 3 for row in rows) or not table.get("headers")
        if malformed:
            # Keep the complete physical evidence in raw_grid.json. The
            # baseline fact builder requires a 3-column accounting row, so a
            # malformed/non-financial physical table is isolated from facts.
            result = {"status": "needs_review", "errors": ["physical table has incomplete/non-financial rows"], "source_grid": {**table, "headers": [], "rows": [], "cell_sources": []}}
        else:
            try:
                result = map_table(table)
            except (IndexError, TypeError, KeyError) as exc:
                result = {"status": "needs_review", "errors": [f"semantic_mapper: {exc}"], "source_grid": {**table, "headers": [], "rows": [], "cell_sources": []}}
        # map_table's reusable contract is retained; its FPT document constant
        # is not used as source evidence, so metadata is supplied here.
        result.setdefault("source_grid", table)
        if isinstance(result.get("document"), dict):
            result["document"] = {
                **result["document"], "ticker": ticker, "source_pdf": str(pdf),
                "report_period": f"Q{quarter}_{year}" if quarter else f"YEAR_{year}",
            }
        mapped.append(result)
    return {"schema": "financial_canonical_mapping_v1", "tables": mapped}


def write_page_review_files(mapping: dict[str, Any], images: list[Path], intermediate: Path) -> tuple[Path, Path, float]:
    started = time.perf_counter()
    queues: list[dict[str, Any]] = []
    for page_number, image in enumerate(images, start=1):
        page_tables = [table for table in mapping.get("tables", []) if table.get("source_grid", {}).get("source", {}).get("page") == page_number]
        if not page_tables:
            continue
        page_mapping = {"schema": mapping["schema"], "tables": page_tables}
        path = intermediate / f"page_{page_number:04d}_semantic_mapping.json"
        path.write_text(json.dumps(page_mapping, ensure_ascii=False, indent=2), encoding="utf-8")
        queue = intermediate / f"page_{page_number:04d}_review_queue.json"
        run_stage("review_queue", [sys.executable, str(ROOT / "financial_ocr_mvp/docling_pipeline/cell_retry_ocr.py"), str(path), str(queue)])
        v1 = intermediate / f"page_{page_number:04d}_rapidocr.json"
        run_stage("rapidocr", [sys.executable, str(CELL_RETRY), str(queue), str(image), str(v1)])
        v2 = intermediate / f"page_{page_number:04d}_rapidocr_v2.json"
        run_stage("rapidocr_v2", [sys.executable, str(CELL_RETRY_V2), str(v1), str(image), str(v2)])
        merged = intermediate / f"page_{page_number:04d}_merged.json"
        run_stage("merge_rapidocr", [sys.executable, str(MERGE), str(v1), str(v2), str(merged)])
        queues.append(json.loads(merged.read_text(encoding="utf-8")))
    items = [item for queue in queues for item in queue.get("items", [])]
    merged_path = intermediate / "merged_ocr_candidates.json"
    merged_path.write_text(json.dumps({"schema": "merged_rapidocr_candidates_v1", "items": items}, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged_path, intermediate / "semantic_mapping.json", round(time.perf_counter() - started, 3)


def run_pipeline(pdf: Path, output_dir: Path, ticker: str, year: int, quarter: int | None, report_type: str, source_path: str | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    raw = output_dir / "raw"
    intermediate = output_dir / "intermediate"
    raw.mkdir(parents=True, exist_ok=True)
    intermediate.mkdir(parents=True, exist_ok=True)
    timings: dict[str, float] = {}
    current_stage = "docling"
    try:
        stage_started = time.perf_counter()
        images = render_pages(pdf, raw / "pages")
        grid, _ = extract_page_tables(images, raw, pdf)
        timings["docling"] = round(time.perf_counter() - stage_started, 3)

        current_stage = "semantic_mapping"
        stage_started = time.perf_counter()
        mapping = build_mapping(grid, pdf, ticker, year, quarter)
        mapping_path = intermediate / "semantic_mapping.json"
        mapping_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
        timings["semantic_mapping"] = round(time.perf_counter() - stage_started, 3)

        current_stage = "rapidocr"
        merged_path, _, rapidocr_seconds = write_page_review_files(mapping, images, intermediate)
        timings["rapidocr"] = rapidocr_seconds

        current_stage = "financial_validation"
        stage_started = time.perf_counter()
        validation_path = intermediate / "financial_validation_v3_report.json"
        run_stage("financial_validation", [sys.executable, str(CONSISTENCY), str(mapping_path), str(merged_path), str(validation_path)])
        timings["financial_validation"] = round(time.perf_counter() - stage_started, 3)

        current_stage = "financial_facts"
        stage_started = time.perf_counter()
        facts_v1 = intermediate / "financial_fact_v1.json"
        run_stage("financial_facts", [sys.executable, str(FACT_BUILDER), str(mapping_path), str(merged_path), str(validation_path), str(facts_v1)])
        timings["financial_facts"] = round(time.perf_counter() - stage_started, 3)

        current_stage = "semantic_mapping"
        stage_started = time.perf_counter()
        facts_v2 = intermediate / "financial_fact_v2.json"
        run_stage("semantic_mapping", [sys.executable, str(SEMANTIC), str(facts_v1), str(facts_v2)])
        timings["semantic_mapping"] = round(timings["semantic_mapping"] + time.perf_counter() - stage_started, 3)

        current_stage = "financial_rules"
        stage_started = time.perf_counter()
        rules = intermediate / "financial_validation_rules.json"
        run_stage("financial_rules", [sys.executable, str(RULES), str(facts_v2), str(rules)])
        timings["financial_rules"] = round(time.perf_counter() - stage_started, 3)

        current_stage = "canonical"
        stage_started = time.perf_counter()
        canonical = output_dir / "canonical_financial.json"
        command = [sys.executable, str(CANONICAL), str(facts_v2), str(canonical), "--rules-report", str(rules), "--ticker", ticker, "--year", str(year)]
        if quarter is not None:
            command += ["--quarter", str(quarter)]
        run_stage("canonical", command)
        timings["canonical"] = round(time.perf_counter() - stage_started, 3)
        document = json.loads(canonical.read_text(encoding="utf-8"))
        canonical_status = document.get("status", "needs_review")
        document.setdefault("document", {}).setdefault("source", {})
        document["document"]["source"].update({"input": source_path or str(pdf), "minio_source_path": source_path, "local_pdf": str(pdf)})
        canonical.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"status": "completed", "canonical_path": str(canonical), "facts": len(document.get("facts", [])), "validation_rules": len(json.loads(rules.read_text(encoding="utf-8")).get("rules", [])), "canonical_status": canonical_status, "processing_seconds": round(time.perf_counter() - started, 3), "stage_timings_seconds": timings, "peak_ram_mb": peak_ram_mb(), "error": None}
    except Exception as exc:
        return {"status": "failed", "failed_stage": current_stage, "processing_seconds": round(time.perf_counter() - started, 3), "stage_timings_seconds": timings, "peak_ram_mb": peak_ram_mb(), "error": str(exc)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the isolated financial OCR baseline")
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--quarter", type=int)
    parser.add_argument("--report-type", choices=("quarterly", "annual"), required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-path")
    args = parser.parse_args()
    result = run_pipeline(args.pdf, args.output_dir, args.ticker, args.year, args.quarter, args.report_type, args.source_path)
    result_path = args.output_dir / "pipeline_result.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
