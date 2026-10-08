"""Preflight and apply additive canonical catalog/mapping/serving tables."""

from __future__ import annotations

import os
import re
from pathlib import Path

import psycopg
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "financial_ocr_mvp" / "database" / "migration_vnstock_canonical_serving.sql"
TARGETS = ("vnstock_metric_catalog", "vnstock_metric_mapping", "vnstock_serving_facts")


def env_url() -> str:
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        match = re.match(r"^DATABASE_URL\s*=\s*(.*)$", line)
        if match:
            value = match.group(1).strip()
            return value[1:-1] if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'" else value
    raise SystemExit("DATABASE_URL is not configured")


def main() -> int:
    with psycopg.connect(env_url(), connect_timeout=5, row_factory=dict_row) as conn:
        db = conn.execute("SELECT current_database() AS database, current_user AS user").fetchone()
        if db["database"] != "fireant_stock_dev":
            raise SystemExit(f"Preflight failed: unexpected database {db['database']!r}")
        if not conn.execute("SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname='financial') AS exists").fetchone()["exists"]:
            raise SystemExit("Preflight failed: schema financial does not exist")
        existing = [name for name in TARGETS if conn.execute("SELECT to_regclass(%s) IS NOT NULL AS exists", (f"financial.{name}",)).fetchone()["exists"]]
        if existing:
            raise SystemExit(f"Preflight failed: target(s) already exist; inspect first: {', '.join(existing)}")
        print(f"Preflight PASS: database={db['database']}, targets absent")
        conn.execute(MIGRATION.read_text(encoding="utf-8"))
        conn.commit()
        checks = {name: conn.execute("SELECT to_regclass(%s) IS NOT NULL AS exists", (f"financial.{name}",)).fetchone()["exists"] for name in TARGETS}
        if not all(checks.values()):
            raise SystemExit(f"Migration verification failed: {checks}")
        print(f"Migration applied: {checks}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
