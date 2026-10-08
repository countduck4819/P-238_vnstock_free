"""Report queue state without changing jobs."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def build_report() -> dict[str, object]:
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        rows = conn.execute(
            "SELECT status, count(*) FROM financial.financial_ingestion_jobs GROUP BY status"
        ).fetchall()
    counts = {status: int(count) for status, count in rows}
    total = sum(counts.values())
    completed = counts.get("completed", 0)
    return {
        "total_jobs": total,
        "completed": completed,
        "failed": counts.get("failed", 0),
        "pending": counts.get("pending", 0),
        "processing": counts.get("processing", 0),
        "retry": counts.get("retry", 0),
        "success_rate": round(completed / total, 4) if total else 0.0,
        "by_status": counts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Show financial ingestion status")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_report()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
