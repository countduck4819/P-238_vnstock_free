"""Read-only PostgreSQL catalog inspection for P-238.

Every database statement in this script is metadata or SELECT-only.  It sets
the session to read-only and writes an inventory/report outside the database.
"""

from __future__ import annotations

import argparse
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[2]
META = ROOT / "data" / "vnstock" / "metadata"
REPORT = META / "postgres_schema_report.md"
INVENTORY = META / "postgres_schema_inventory.csv"


def load_env_file() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$", raw)
        if match and match.group(1) not in os.environ:
            value = match.group(2).strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            os.environ[match.group(1)] = value


def connect() -> psycopg.Connection:
    load_env_file()
    url = os.environ.get("DATABASE_URL")
    if url:
        return psycopg.connect(url, connect_timeout=5, options="-c default_transaction_read_only=on", row_factory=dict_row)
    kwargs = {
        "host": os.environ.get("PGHOST", "127.0.0.1"),
        "port": int(os.environ.get("PGPORT", "5432")),
        "dbname": os.environ.get("POSTGRES_DB", "postgres"),
        "user": os.environ.get("POSTGRES_USER"),
        "password": os.environ.get("POSTGRES_PASSWORD"),
        "connect_timeout": 5,
        "options": "-c default_transaction_read_only=on",
        "row_factory": dict_row,
    }
    return psycopg.connect(**{key: value for key, value in kwargs.items() if value is not None})


def q_all(conn: psycopg.Connection, query: str, params: tuple = ()) -> list[dict]:
    return list(conn.execute(query, params).fetchall())


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only PostgreSQL schema inspection")
    parser.parse_args()
    META.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
        database = conn.execute("SELECT current_database() AS database, current_user AS user, current_setting('transaction_read_only') AS read_only").fetchone()
        schemas = q_all(conn, "SELECT nspname AS schema FROM pg_namespace WHERE nspname NOT LIKE 'pg_%%' AND nspname <> 'information_schema' ORDER BY nspname")
        objects = q_all(conn, """
            SELECT table_schema AS schema, table_name AS name, table_type AS object_type
            FROM information_schema.tables
            WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
            UNION ALL
            SELECT schemaname, matviewname, 'MATERIALIZED VIEW'
            FROM pg_matviews
            ORDER BY 1, 2
        """)
        tables = q_all(conn, """
            SELECT n.nspname AS schema, c.relname AS table_name,
                   c.reltuples::bigint AS estimated_row_count,
                   c.relkind
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind IN ('r','p') AND n.nspname NOT IN ('pg_catalog','information_schema')
            ORDER BY n.nspname, c.relname
        """)
        columns = q_all(conn, """
            SELECT table_schema AS schema, table_name, column_name, data_type,
                   udt_name, is_nullable, ordinal_position
            FROM information_schema.columns
            WHERE table_schema NOT IN ('pg_catalog','information_schema')
            ORDER BY table_schema, table_name, ordinal_position
        """)
        constraints = q_all(conn, """
            SELECT n.nspname AS schema, c.relname AS table_name, con.conname AS constraint_name,
                   CASE con.contype WHEN 'p' THEN 'PRIMARY KEY' WHEN 'u' THEN 'UNIQUE'
                        WHEN 'f' THEN 'FOREIGN KEY' WHEN 'x' THEN 'EXCLUDE' ELSE con.contype::text END AS constraint_type,
                   pg_get_constraintdef(con.oid) AS definition
            FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid
                 JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname NOT IN ('pg_catalog','information_schema')
            ORDER BY 1,2,3
        """)
        indexes = q_all(conn, """
            SELECT schemaname AS schema, tablename AS table_name, indexname, indexdef
            FROM pg_indexes
            WHERE schemaname NOT IN ('pg_catalog','information_schema')
            ORDER BY schemaname, tablename, indexname
        """)
        sequences = q_all(conn, """
            SELECT sequence_schema AS schema, sequence_name, data_type
            FROM information_schema.sequences
            WHERE sequence_schema NOT IN ('pg_catalog','information_schema')
            ORDER BY 1,2
        """)
        # Actual COUNT(*) is restricted to relevant tables and remains read-only.
        relevant_names = ("financial", "finance", "fact", "metric", "statement", "company", "ticker", "document", "embedding", "vnstock")
        relevant_tables = [table for table in tables if any(token in table["table_name"].lower() for token in relevant_names)]
        for table in relevant_tables:
            table["actual_row_count"] = conn.execute(sql.SQL("SELECT count(*) AS count FROM {}.{};").format(sql.Identifier(table["schema"]), sql.Identifier(table["table_name"]))).fetchone()["count"]

    column_by_table: dict[tuple[str, str], list[dict]] = {}
    for column in columns:
        column_by_table.setdefault((column["schema"], column["table_name"]), []).append(column)
    constraints_by_table: dict[tuple[str, str], list[dict]] = {}
    for constraint in constraints:
        constraints_by_table.setdefault((constraint["schema"], constraint["table_name"]), []).append(constraint)
    indexes_by_table: dict[tuple[str, str], list[dict]] = {}
    for index in indexes:
        indexes_by_table.setdefault((index["schema"], index["table_name"]), []).append(index)

    inventory_rows = []
    for table in relevant_tables:
        key = (table["schema"], table["table_name"])
        table_constraints = constraints_by_table.get(key, [])
        primary = [item for item in table_constraints if item["constraint_type"] == "PRIMARY KEY"]
        unique = [item for item in table_constraints if item["constraint_type"] == "UNIQUE"]
        indexed_columns = " ".join(index["indexdef"] for index in indexes_by_table.get(key, []))
        for column in column_by_table.get(key, []):
            inventory_rows.append({
                "schema": table["schema"], "table": table["table_name"], "column": column["column_name"],
                "data_type": column["data_type"], "udt_name": column["udt_name"], "nullable": column["is_nullable"],
                "primary_key": any(column["column_name"] in item["definition"] for item in primary),
                "unique": any(column["column_name"] in item["definition"] for item in unique),
                "indexed": column["column_name"] in indexed_columns,
                "estimated_row_count": table["estimated_row_count"], "actual_row_count": table.get("actual_row_count", ""),
            })
    import csv
    with INVENTORY.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(inventory_rows[0]) if inventory_rows else ["schema", "table", "column", "data_type", "udt_name", "nullable", "primary_key", "unique", "indexed", "estimated_row_count", "actual_row_count"])
        writer.writeheader()
        writer.writerows(inventory_rows)

    relevant_table_names = {f"{table['schema']}.{table['table_name']}" for table in relevant_tables}
    lines = [
        "# PostgreSQL Schema Inspection — P-238", "", f"Generated: {datetime.now(timezone.utc).astimezone().isoformat()}", "",
        "## 1. Connection/config source", "",
        "- Source: project `.env` (`DATABASE_URL`); credentials intentionally omitted.",
        f"- Database: `{database['database']}`; user: `{database['user']}`; transaction mode: `{database['read_only']}`.",
        "- Inspection used catalog queries and SELECT only. No write statement was executed.", "",
        "## 2. Schemas and objects", "",
        "Schemas: " + ", ".join(f"`{item['schema']}`" for item in schemas) + ".", "",
        "| Schema | Object | Type |", "|---|---|---|",
    ]
    lines += [f"| {item['schema']} | {item['name']} | {item['object_type']} |" for item in objects]
    lines += ["", "## 3. Relevant table inventory", ""]
    if not relevant_tables:
        lines.append("No existing table matched financial/fact/metric/statement/company/ticker/document/embedding/vnstock naming patterns.")
    for table in relevant_tables:
        key = (table["schema"], table["table_name"])
        cons = constraints_by_table.get(key, [])
        idx = indexes_by_table.get(key, [])
        lines += [f"### `{table['schema']}.{table['table_name']}`", "", f"- Estimated rows: `{table['estimated_row_count']}`; actual rows: `{table.get('actual_row_count', 'not counted')}`.", "- Columns:"]
        lines += [f"  - `{column['column_name']}` {column['data_type']} ({'NULL' if column['is_nullable']=='YES' else 'NOT NULL'})" for column in column_by_table.get(key, [])]
        lines.append("- Constraints: " + ("; ".join(f"`{item['constraint_name']}` {item['constraint_type']}: {item['definition']}" for item in cons) if cons else "none"))
        lines.append("- Indexes: " + ("; ".join(f"`{item['indexname']}`: {item['indexdef']}" for item in idx) if idx else "none"))
    lines += ["", "## 4. Existing financial architecture and reuse recommendation", ""]
    if relevant_tables:
        lines.append("The existing `financial` tables are an OCR/text-document ingestion architecture: `document_registry` tracks extracted TXT/PDF documents, `financial_documents` stores canonical JSON documents, and `financial_facts` stores document-scoped text facts with `(document_id, fact_id)` uniqueness. They are not the VCI Parquet evidence contract.")
        lines.append("")
        lines.append("| Existing object | Recommendation | Rationale |")
        lines.append("|---|---|---|")
        lines.append("| `financial.document_registry` | KEEP_SEPARATE | Legacy document provenance; different source contract. |")
        lines.append("| `financial.financial_documents` | KEEP_SEPARATE | OCR/document JSON, not VCI row evidence. |")
        lines.append("| `financial.financial_facts` | KEEP_SEPARATE / DEPRECATED_CANDIDATE | Text-valued, document-scoped facts; key is unsuitable for VCI item conflicts. |")
        lines.append("| `financial.financial_ingestion_jobs` | KEEP_SEPARATE | Existing OCR ingestion job lifecycle. |")
        lines.append("| `financial.financial_validation` | KEEP_SEPARATE | Validation tied to legacy document IDs. |")
        lines.append("")
        lines.append("Recommendation: **NEW TABLES** for VCI normalized evidence and canonical serving facts. Reuse legacy tables only for their existing OCR workload; do not mix source domains.")
    else:
        lines.append("No existing relevant financial/facts/metrics table was found. Recommendation: **NEW TABLES** for a VCI normalized evidence layer and a separate canonical serving layer; confirm this against deployment/container state before migration.")
    lines += ["", "## 5. Evidence-layer recommendation", "", "Create an additive evidence table only after approval, with an independent identity and provenance: `evidence_id`, `ticker`, `year`, `statement_type`, `source`, `source_item_id`, `source_item_name`, `source_item_name_en`, `source_row_index`, `value`, `raw_snapshot_id`, `ingested_at`. Do not make `(ticker, year, statement_type, source_item_id)` unique; conflict review found multiple values and labels. Preserve source-row traceability.", "", "## 6. Serving-layer recommendation", "", "Use a separate canonical serving table (for example `financial_serving_facts`) with `ticker`, `year`, `canonical_metric_code`, `value`, `source_evidence_id`, `updated_at`. Its unique key can be `(ticker, year, canonical_metric_code)` only after deterministic canonical mapping rules and conflict policy are manually approved.", "", "## 7. Required additive migrations", "", "1. Add evidence table and provenance indexes (no destructive migration).  2. Add mapping/catalog tables only after source-to-canonical rules are approved.  3. Add serving facts table only after canonical mapping.  4. Add read-only serving role and migration checks before loading data.", "", "## 8. Performance/connection recommendations", "", "- Use a connection pool in serving code; do not open a new connection per request.", "- Candidate indexes after real benchmark: evidence `(ticker, statement_type, year, source_item_id)`; serving `(ticker, year, canonical_metric_code)`, `(ticker, canonical_metric_code, year)`, `(year, canonical_metric_code, value)`.", "- Keep candidate indexes minimal until query plans and ingestion cost are measured.", "", "## 9. Risks and phase gate", "", "- VCI `item_id` is a source identifier, not yet a canonical identity.", "- Existing legacy schema semantics may differ from VCI normalized evidence.", "- Do not load the pilot until evidence identity/conflict handling is approved.", "- **PASS for read-only inspection; STOP before migration/load.** Next permitted phase: design/review additive evidence migration, then PostgreSQL Evidence Pilot Load.", ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
