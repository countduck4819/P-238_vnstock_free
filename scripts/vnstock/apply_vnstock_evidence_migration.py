"""Preflight and apply the additive VCI evidence migration exactly once."""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

import psycopg
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "financial_ocr_mvp" / "database" / "migration_vnstock_evidence.sql"


def load_env() -> str:
    env = dict(os.environ)
    path = ROOT / ".env"
    if path.exists():
        for raw in path.read_text(encoding="utf-8").splitlines():
            match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$", raw)
            if match and match.group(1) not in env:
                value = match.group(2).strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                env[match.group(1)] = value
    if env.get("DATABASE_URL"):
        return env["DATABASE_URL"]
    raise SystemExit("DATABASE_URL is not configured")


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply additive VCI evidence migration after strict preflight")
    parser.parse_args()
    with psycopg.connect(load_env(), connect_timeout=5, row_factory=dict_row) as conn:
        database = conn.execute("SELECT current_database() AS database, current_user AS user").fetchone()
        if database["database"] != "fireant_stock_dev":
            raise SystemExit(f"Preflight failed: unexpected database {database['database']!r}")
        schema_exists = conn.execute("SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname='financial') AS exists").fetchone()["exists"]
        if not schema_exists:
            raise SystemExit("Preflight failed: schema financial does not exist")
        target_exists = conn.execute("SELECT to_regclass('financial.vnstock_financial_evidence') IS NOT NULL AS exists").fetchone()["exists"]
        if target_exists:
            raise SystemExit("Preflight failed: target table already exists; inspect it before any migration")
        print(f"Preflight PASS: database={database['database']}, user={database['user']}, schema=financial, target=absent")
        conn.execute(MIGRATION.read_text(encoding="utf-8"))
        conn.commit()
        verified = conn.execute("""
            SELECT c.oid IS NOT NULL AS table_exists,
                   (SELECT count(*) FROM pg_indexes WHERE schemaname='financial' AND tablename='vnstock_financial_evidence') AS index_count
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='financial' AND c.relname='vnstock_financial_evidence'
        """).fetchone()
        if not verified or not verified["table_exists"] or verified["index_count"] < 4:
            raise SystemExit("Migration verification failed")
        print(f"Migration applied: table_exists={verified['table_exists']}, index_count={verified['index_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
