"""Build a database/RAG-friendly canonical financial document.

This is an organizational step only: values and evidence are copied unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

STATEMENT_TYPES = ("income_statement", "balance_sheet", "cash_flow")


def fact_id(fact: dict[str, Any]) -> str:
    source = fact.get("source", {})
    raw = "|".join(str(value) for value in (
        fact.get("concept", ""),
        fact.get("period", ""),
        source.get("page", ""),
        source.get("table", ""),
        source.get("row", ""),
        source.get("column", ""),
    ))
    return "fact_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def canonical_fact(fact: dict[str, Any]) -> dict[str, Any]:
    # Explicit fields make the output stable for SQL and RAG ingestion while
    # preserving the original evidence fields.
    result = {
        "fact_id": fact_id(fact),
        "concept": fact.get("concept"),
        "metric": fact.get("metric"),
        "statement_type": fact.get("statement_type", "unknown"),
        "financial_category": fact.get("financial_category", "unknown"),
        "code": fact.get("code", ""),
        "period": fact.get("period", ""),
        "value": fact.get("value", fact.get("final_value", "")),
        "final_value": fact.get("final_value", fact.get("value", "")),
        "raw_value": fact.get("raw_value", ""),
        "candidate_value": fact.get("candidate_value", ""),
        "confidence": fact.get("confidence", 0.0),
        "status": fact.get("status", "needs_review"),
        "verification_status": fact.get("verification_status", fact.get("status", "needs_review")),
        "source": fact.get("source", {}),
        "column": fact.get("column", {}),
        "reason": fact.get("reason", ""),
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Build canonical financial JSON")
    parser.add_argument("facts", type=Path, help="financial_fact_v2.json")
    parser.add_argument("output", type=Path, help="canonical_financial.json")
    parser.add_argument("--rules-report", type=Path, default=None)
    parser.add_argument("--ticker", default=None)
    parser.add_argument("--company-name", default=None)
    parser.add_argument("--year", type=int, default=None)
    parser.add_argument("--quarter", type=int, default=None)
    args = parser.parse_args()

    source_document = json.loads(args.facts.read_text(encoding="utf-8"))
    rules_path = args.rules_report or args.facts.with_name("financial_validation_rules.json")
    rules_document = json.loads(rules_path.read_text(encoding="utf-8")) if rules_path.exists() else {"summary": {}}

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    all_facts: list[dict[str, Any]] = []
    for fact in source_document.get("facts", []):
        canonical = canonical_fact(fact)
        statement = canonical["statement_type"]
        groups[statement].append(canonical)
        all_facts.append(canonical)

    quality = {
        "total_facts": len(all_facts),
        "validation_pass": rules_document.get("summary", {}).get("pass", 0),
        "validation_fail": rules_document.get("summary", {}).get("fail", 0),
        "needs_review": sum(fact["status"] == "needs_review" for fact in all_facts),
        "candidates": sum(fact["status"] == "candidate" for fact in all_facts),
        "verified": sum(fact["status"] == "verified" for fact in all_facts),
    }

    statements = {
        statement: {
            "statement_type": statement,
            "fact_count": len(groups.get(statement, [])),
            "facts": groups.get(statement, []),
        }
        for statement in STATEMENT_TYPES
    }
    for statement, facts in groups.items():
        if statement not in statements:
            statements[statement] = {
                "statement_type": statement,
                "fact_count": len(facts),
                "facts": facts,
            }

    source_metadata = {
        "ticker": args.ticker,
        "company_name": args.company_name,
        "year": args.year,
        "quarter": args.quarter,
        "reporting_period": f"Q{args.quarter}_{args.year}" if args.quarter and args.year else None,
    }
    output = {
        "schema": "canonical_financial_v1",
        "status": "needs_review" if quality["needs_review"] else "ready",
        "document": {
            "source": source_document.get("provenance", {}),
            "statement_types": list(statements),
            **{key: value for key, value in source_metadata.items() if value is not None},
        },
        "quality_summary": quality,
        "statements": statements,
        "facts": all_facts,
        "policy": {
            "raw_value_overwrite": False,
            "candidate_preserved": True,
            "numeric_normalization": False,
            "source_trace_preserved": True,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Saved:", args.output)
    print(quality)


if __name__ == "__main__":
    main()
