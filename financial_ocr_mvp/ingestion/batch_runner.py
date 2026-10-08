"""Run queued jobs through the existing document pipeline.

The existing OCR pipeline is intentionally invoked as an external command. Set
``FINANCIAL_PIPELINE_COMMAND`` to a command template containing ``{pdf_path}``,
``{ticker}``, ``{year}``, ``{quarter}``, and ``{output_dir}``. The command must
write ``canonical_financial.json`` into ``output_dir``. This keeps orchestration
separate from Docling/RapidOCR/canonicalization code.
"""
from __future__ import annotations

import argparse
import logging
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from financial_ocr_mvp.ingestion.ingestion_manager import minio_client

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
MAX_RETRIES = 3
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(filename=LOG_DIR / "batch_runner.log", level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOGGER = logging.getLogger(__name__)


def claim_job(conn: psycopg.Connection) -> dict[str, object] | None:
    with conn.transaction():
        row = conn.execute(
            """SELECT id, ticker, year, quarter, report_type, source_path, retry_count
            FROM financial.financial_ingestion_jobs
            WHERE status IN ('pending', 'retry') AND retry_count < %s
            ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1""",
            (MAX_RETRIES,),
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            """UPDATE financial.financial_ingestion_jobs
            SET status='processing', started_at=now(), updated_at=now()
            WHERE id=%s""",
            (row[0],),
        )
    return dict(zip(("id", "ticker", "year", "quarter", "report_type", "source_path", "retry_count"), row))


def finish(conn: psycopg.Connection, job_id: int, status: str, error: str | None = None) -> None:
    conn.execute(
        """UPDATE financial.financial_ingestion_jobs
        SET status=%s, error_message=%s, completed_at=CASE WHEN %s='completed' THEN now() ELSE NULL END,
            retry_count=CASE WHEN %s='completed' THEN retry_count ELSE retry_count+1 END, updated_at=now()
        WHERE id=%s""",
        (status, error, status, status, job_id),
    )
    conn.commit()


def process_job(conn: psycopg.Connection, job: dict[str, object], command: str) -> None:
    client, bucket = minio_client()
    with tempfile.TemporaryDirectory(prefix=f"financial_job_{job['id']}_") as temp:
        workdir = Path(temp)
        pdf_path = workdir / Path(str(job["source_path"])).name
        output_dir = workdir / "output"
        output_dir.mkdir()
        with pdf_path.open("wb") as stream:
            client.fget_object(bucket, str(job["source_path"]), str(pdf_path))
        values = {
            "pdf_path": str(pdf_path), "ticker": job["ticker"], "year": job["year"],
            "quarter": job["quarter"] or "YEAR", "output_dir": str(output_dir),
        }
        args = [part.format(**values) for part in shlex.split(command)]
        subprocess.run(args, cwd=ROOT, check=True)
        canonical = output_dir / "canonical_financial.json"
        if not canonical.exists():
            raise RuntimeError(f"Pipeline không tạo {canonical}")
        importer = ROOT / "financial_ocr_mvp" / "database" / "import_canonical_to_postgres.py"
        subprocess.run([os.environ.get("PYTHON", sys.executable), str(importer), str(canonical)], cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Process financial ingestion jobs")
    parser.add_argument("--once", action="store_true", help="process one job")
    parser.add_argument("--pipeline-command", default=os.getenv("FINANCIAL_PIPELINE_COMMAND"))
    args = parser.parse_args()
    if not args.pipeline_command:
        parser.error("cần --pipeline-command hoặc FINANCIAL_PIPELINE_COMMAND")
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        while True:
            job = claim_job(conn)
            if not job:
                break
            try:
                LOGGER.info("processing job=%s source=%s", job["id"], job["source_path"])
                process_job(conn, job, args.pipeline_command)
                finish(conn, int(job["id"]), "completed")
            except Exception as exc:  # keep queue alive and make retry explicit
                LOGGER.exception("job=%s failed", job["id"])
                next_status = "failed" if int(job["retry_count"]) + 1 >= MAX_RETRIES else "retry"
                finish(conn, int(job["id"]), next_status, str(exc))
            if args.once:
                break


if __name__ == "__main__":
    main()
