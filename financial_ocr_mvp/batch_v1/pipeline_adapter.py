"""MinIO read-only adapter around the isolated baseline pipeline."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import psycopg

from .config import OUTPUT_DIR, BUCKET
from .minio_scanner import make_client
from .run_financial_pipeline import run_pipeline

ROOT = Path(__file__).resolve().parents[2]
IMPORTER = ROOT / "financial_ocr_mvp/database/import_canonical_to_postgres.py"


class PipelineAdapter:
    def __init__(self, bucket: str = BUCKET) -> None:
        self.bucket = bucket
        self.client = make_client()

    def process(self, job: dict[str, Any]) -> dict[str, Any]:
        quarter = job.get("quarter")
        period_dir = f"Q{quarter}" if quarter else "YEAR"
        output_dir = OUTPUT_DIR / str(job["ticker"]) / str(job["year"]) / period_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        source_path = str(job["source_path"])
        job_started = time.perf_counter()
        import tempfile
        with tempfile.TemporaryDirectory(prefix=f"batch_v1_job_{job['id']}_") as temp:
            pdf_path = Path(temp) / Path(source_path).name
            download_started = time.perf_counter()
            self.client.fget_object(self.bucket, source_path, str(pdf_path))
            download_seconds = round(time.perf_counter() - download_started, 3)
            result = run_pipeline(pdf_path, output_dir, str(job["ticker"]), int(job["year"]), int(quarter) if quarter is not None else None, str(job["report_type"]), source_path)
        result.setdefault("stage_timings_seconds", {})["download"] = download_seconds
        (output_dir / "pipeline_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        if result.get("status") != "completed":
            return {"download": "PASS", **result}
        canonical = Path(result["canonical_path"])
        validation = output_dir / "intermediate" / "financial_validation_rules.json"
        command = [sys.executable, str(IMPORTER), str(canonical)]
        if validation.exists():
            command += ["--validation-report", str(validation)]
        try:
            import_started = time.perf_counter()
            subprocess.run(command, cwd=ROOT, check=True)
            import_seconds = round(time.perf_counter() - import_started, 3)
        except Exception as exc:
            result.setdefault("stage_timings_seconds", {})["postgres_import"] = round(time.perf_counter() - import_started, 3)
            result["processing_seconds"] = round(time.perf_counter() - job_started, 3)
            result.update({"download": "PASS", "status": "failed", "failed_stage": "postgres_import", "error": str(exc)})
            (output_dir / "pipeline_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            return result
        result.setdefault("stage_timings_seconds", {})["postgres_import"] = import_seconds
        result["processing_seconds"] = round(time.perf_counter() - job_started, 3)
        result["download"] = "PASS"
        result["postgres_import"] = "PASS"
        (output_dir / "pipeline_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result


def update_job(conn: psycopg.Connection, job_id: int, status: str, result: dict[str, Any]) -> None:
    conn.execute("""UPDATE financial.financial_ingestion_jobs
        SET status=%s, error_message=%s, completed_at=now(), updated_at=now(),
            retry_count=CASE WHEN %s IN ('completed','needs_review') THEN retry_count ELSE retry_count+1 END
        WHERE id=%s""", (status, result.get("error"), status, job_id))
    conn.commit()
