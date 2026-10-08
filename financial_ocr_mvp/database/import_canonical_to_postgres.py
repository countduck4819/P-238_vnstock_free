"""Import canonical_financial.json into the existing database financial schema."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

try:
    import psycopg
    from psycopg.types.json import Jsonb
except ImportError as exc:  # pragma: no cover
    raise SystemExit('Install dependency first: pip install "psycopg[binary]"') from exc


def load_dotenv_fallback(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def document_hash(document: dict[str, Any]) -> str:
    payload = json.dumps(document, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def document_metadata(document: dict[str, Any]) -> tuple[str, str | None, str | None, str | None, int | None, int | None]:
    metadata = document.get("document", {})
    source = metadata.get("source", {})
    facts = document.get("facts", [])
    periods = [str(fact.get("period")) for fact in facts if fact.get("period")]
    return (
        str(source.get("input") or source.get("pdf") or ""),
        metadata.get("company_name"),
        metadata.get("ticker"),
        metadata.get("reporting_period") or (periods[0] if periods else None),
        metadata.get("year"),
        metadata.get("quarter"),
    )


def upsert_document(cursor: Any, document: dict[str, Any]) -> int:
    source_pdf, company_name, ticker, period, report_year, quarter = document_metadata(document)
    cursor.execute("SELECT id FROM financial.financial_documents WHERE source_pdf = %s ORDER BY id LIMIT 1", (source_pdf,))
    existing = cursor.fetchone()
    if existing is not None:
        cursor.execute(
            """
            UPDATE financial.financial_documents
            SET company_name=%s, ticker=%s, period=%s, report_year=%s,
                quarter=%s, status=%s, quality_summary=%s,
                canonical_document=%s, updated_at=NOW()
            WHERE id=%s
            """,
            (company_name, ticker, period, report_year, quarter,
             document.get("status", "needs_review"),
             Jsonb(document.get("quality_summary", {})), Jsonb(document), existing[0]),
        )
        return int(existing[0])
    cursor.execute(
        """
        INSERT INTO financial.financial_documents (
            document_hash, source_pdf, company_name, ticker, period,
            report_year, quarter, status, quality_summary, canonical_document
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (document_hash) DO UPDATE SET
            source_pdf = EXCLUDED.source_pdf,
            company_name = EXCLUDED.company_name,
            ticker = EXCLUDED.ticker,
            period = EXCLUDED.period,
            report_year = EXCLUDED.report_year,
            quarter = EXCLUDED.quarter,
            status = EXCLUDED.status,
            quality_summary = EXCLUDED.quality_summary,
            canonical_document = EXCLUDED.canonical_document,
            updated_at = NOW()
        RETURNING id
        """,
        (
            document_hash(document),
            source_pdf,
            company_name,
            ticker,
            period,
            report_year,
            quarter,
            document.get("status", "needs_review"),
            Jsonb(document.get("quality_summary", {})),
            Jsonb(document),
        ),
    )
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError("Could not obtain financial document id")
    return int(row[0])


def upsert_facts(cursor: Any, document_id: int, facts: list[dict[str, Any]]) -> int:
    for fact in facts:
        cursor.execute(
            """
            INSERT INTO financial.financial_facts (
                document_id, fact_id, concept, metric, statement_type,
                financial_category, code, period, value, final_value,
                raw_value, candidate_value, confidence, status,
                verification_status, source, column_info, reason
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (document_id, fact_id) DO UPDATE SET
                concept = EXCLUDED.concept,
                metric = EXCLUDED.metric,
                statement_type = EXCLUDED.statement_type,
                financial_category = EXCLUDED.financial_category,
                code = EXCLUDED.code,
                period = EXCLUDED.period,
                value = EXCLUDED.value,
                final_value = EXCLUDED.final_value,
                raw_value = EXCLUDED.raw_value,
                candidate_value = EXCLUDED.candidate_value,
                confidence = EXCLUDED.confidence,
                status = EXCLUDED.status,
                verification_status = EXCLUDED.verification_status,
                source = EXCLUDED.source,
                column_info = EXCLUDED.column_info,
                reason = EXCLUDED.reason,
                updated_at = NOW()
            """,
            (
                document_id,
                fact["fact_id"],
                fact.get("concept", "unknown"),
                fact.get("metric", ""),
                fact.get("statement_type", "unknown"),
                fact.get("financial_category", "unknown"),
                fact.get("code", ""),
                fact.get("period", ""),
                fact.get("value", ""),
                fact.get("final_value", ""),
                fact.get("raw_value", ""),
                fact.get("candidate_value", ""),
                float(fact.get("confidence", 0) or 0),
                fact.get("status", "needs_review"),
                fact.get("verification_status", fact.get("status", "needs_review")),
                Jsonb(fact.get("source", {})),
                Jsonb(fact.get("column", {})),
                fact.get("reason", ""),
            ),
        )
    return len(facts)


def replace_validation(cursor: Any, document_id: int, report: dict[str, Any] | None) -> int:
    if report is None:
        return 0
    cursor.execute("DELETE FROM financial.financial_validation WHERE document_id = %s", (document_id,))
    for rule in report.get("rules", []):
        details = {
            "formula": rule.get("formula"),
            "table": rule.get("table"),
            "column": rule.get("column"),
            "facts_used": rule.get("facts_used", []),
            "reason": rule.get("reason", ""),
        }
        cursor.execute(
            """
            INSERT INTO financial.financial_validation (
                document_id, rule_name, status, expected_value,
                actual_value, details
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                document_id,
                rule.get("rule", ""),
                rule.get("status", "not_applicable"),
                rule.get("expected"),
                rule.get("actual"),
                Jsonb(details),
            ),
        )
    return len(report.get("rules", []))


def main() -> None:
    parser = argparse.ArgumentParser(description="Import canonical financial JSON")
    parser.add_argument("canonical", type=Path)
    parser.add_argument("--validation-report", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args()

    module_path = Path(__file__).resolve()
    for env_path in (module_path.parents[2] / ".env", module_path.parents[1] / ".env"):
        load_dotenv_fallback(env_path)
    document = load_json(args.canonical)
    report = load_json(args.validation_report) if args.validation_report else None
    if args.dry_run:
        print({
            "schema": document.get("schema"),
            "facts": len(document.get("facts", [])),
            "validation_rules": len(report.get("rules", [])) if report else 0,
            "raw_values_overwritten": 0,
        })
        return

    database_url = args.database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is not set")

    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            document_id = upsert_document(cursor, document)
            fact_count = upsert_facts(cursor, document_id, document.get("facts", []))
            validation_count = replace_validation(cursor, document_id, report)
        connection.commit()

    print({
        "document_id": document_id,
        "facts_imported": fact_count,
        "validation_imported": validation_count,
        "raw_values_overwritten": 0,
    })


if __name__ == "__main__":
    main()
