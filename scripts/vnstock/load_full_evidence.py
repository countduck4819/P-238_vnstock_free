"""Bulk-load the full local evidence scale into the existing evidence table."""

from __future__ import annotations

import argparse
import csv
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "vnstock"
EVIDENCE = DATA / "normalized" / "evidence"
META = DATA / "metadata"
LOG = DATA / "logs" / "evidence_scale.log"
PILOT = ("FPT", "HPG", "MWG", "GAS", "ACB", "MBB", "SSI", "BVH")
TARGET_COLUMNS = ["evidence_id", "ticker", "year", "statement_type", "source", "source_item_id", "source_item_name", "source_item_name_en", "source_row_index", "value", "raw_snapshot_id", "source_file"]


def url() -> str:
    if os.environ.get("DATABASE_URL"): return os.environ["DATABASE_URL"]
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        m = re.match(r"^DATABASE_URL\s*=\s*(.*)$", line)
        if m:
            v = m.group(1).strip(); return v[1:-1] if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'" else v
    raise SystemExit("DATABASE_URL is not configured")


def setup_log() -> logging.Logger:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=[logging.FileHandler(LOG, encoding="utf-8")], force=True)
    return logging.getLogger("evidence_loader")


def py(value: Any) -> Any:
    if value is None: return None
    try:
        if bool(pd.isna(value)): return None
    except (TypeError, ValueError): pass
    return value.item() if hasattr(value, "item") else value


def main() -> int:
    parser = argparse.ArgumentParser(description="COPY-load all available VCI evidence artifacts")
    parser.add_argument("--only")
    args = parser.parse_args()
    logger = setup_log()
    tickers = [v.strip().upper() for v in args.only.split(",") if v.strip()] if args.only else None
    if args.only and set(tickers) - set(PILOT):
        raise SystemExit("Invalid ticker selection")
    if tickers is None:
        with (META / "evidence_manifest.csv").open("r", encoding="utf-8", newline="") as handle:
            tickers = [row["ticker"] for row in csv.DictReader(handle)]
    start = time.perf_counter(); loaded = 0
    batch_size = 50
    with psycopg.connect(url(), connect_timeout=10, row_factory=dict_row) as conn:
        db = conn.execute("SELECT current_database() AS database").fetchone()["database"]
        if db != "fireant_stock_dev": raise SystemExit(f"Unexpected database: {db}")
        if not conn.execute("SELECT to_regclass('financial.vnstock_financial_evidence') IS NOT NULL AS exists").fetchone()["exists"]:
            raise SystemExit("Evidence table does not exist")
        for batch_start in range(0, len(tickers), batch_size):
            batch = tickers[batch_start:batch_start + batch_size]
            batch_frames: list[tuple[str, pd.DataFrame]] = []
            for ticker in batch:
                path = EVIDENCE / f"{ticker}.parquet"
                if not path.exists():
                    logger.info("%s skipped (empty/no artifact)", ticker); continue
                frame = pd.read_parquet(path)
                if list(frame.columns) != [*TARGET_COLUMNS, "created_at"]:
                    raise SystemExit(f"{ticker}: unexpected evidence schema")
                batch_frames.append((ticker, frame))
            with conn.transaction():
                stage_name = f"evidence_stage_{batch_start}"
                conn.execute(f"CREATE TEMP TABLE {stage_name} (LIKE financial.vnstock_financial_evidence INCLUDING DEFAULTS) ON COMMIT DROP")
                with conn.cursor() as cursor:
                    with cursor.copy(f"COPY {stage_name} (evidence_id,ticker,year,statement_type,source,source_item_id,source_item_name,source_item_name_en,source_row_index,value,raw_snapshot_id,source_file) FROM STDIN") as copy:
                        for _, frame in batch_frames:
                            for row in frame.itertuples(index=False, name=None):
                                copy.write_row(tuple(py(value) for value in row[:-1]))
                    cursor.execute(f"""INSERT INTO financial.vnstock_financial_evidence
                        (evidence_id,ticker,year,statement_type,source,source_item_id,source_item_name,source_item_name_en,source_row_index,value,raw_snapshot_id,source_file)
                        SELECT evidence_id,ticker,year,statement_type,source,source_item_id,source_item_name,source_item_name_en,source_row_index,value,raw_snapshot_id,source_file
                        FROM {stage_name} ON CONFLICT (evidence_id) DO NOTHING""")
            selected = [ticker for ticker, _ in batch_frames]
            if selected:
                db_counts = {row["ticker"]: row["count"] for row in conn.execute("SELECT ticker,count(*) AS count FROM financial.vnstock_financial_evidence WHERE ticker=ANY(%s) GROUP BY ticker", (selected,)).fetchall()}
                for ticker, frame in batch_frames:
                    if db_counts.get(ticker, 0) != len(frame): raise RuntimeError(f"{ticker}: DB rows {db_counts.get(ticker, 0)} != artifact rows {len(frame)}")
                    loaded += len(frame)
            logger.info("batch %d-%d/%d tickers, artifacts=%d rows", batch_start + 1, min(batch_start + batch_size, len(tickers)), len(tickers), sum(len(frame) for _, frame in batch_frames))
    print(f"Loaded {loaded} rows for {len(tickers)} ticker(s) in {time.perf_counter()-start:.2f}s")
    return 0


if __name__ == "__main__": raise SystemExit(main())
