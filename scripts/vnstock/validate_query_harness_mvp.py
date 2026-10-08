"""Run the bounded deterministic Query Harness MVP validation matrix."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
META = ROOT / "data" / "vnstock" / "metadata"
sys.path.insert(0, str(ROOT))

from src.services.query_harness import QueryHarness

SUMMARY = META / "query_harness_mvp_summary.json"
REPORT = META / "query_harness_mvp_report.md"


def compact(response: dict) -> dict:
    return {
        "tool": response["tool"],
        "status": response["status"],
        "ticker": response["ticker"],
        "tickers": response["tickers"],
        "metric": response["metric"],
        "year": response["year"],
        "period": response["period"],
        "sector": response["sector"],
        "source": response["source"],
        "result_count": len(response["data"]),
        "values": [row.get("value") for row in response["data"]],
        "row_statuses": [row.get("status", row.get("calculation_status")) for row in response["data"]],
        "returned_tickers": [row.get("ticker") for row in response["data"]],
        "returned_document_types": [row.get("document_type") for row in response["data"]],
        "warnings": response["warnings"],
        "errors": response["errors"],
    }


def main() -> int:
    harness = QueryHarness()
    try:
        fact_cases = [
            ("FPT", "net_profit", 2025),
            ("ACB", "net_profit", 2025),
            ("FPT", "net_profit_margin", 2025),
            ("ACB", "roe", 2025),
        ]
        facts = [
            harness.execute_query("FACT", {"ticker": t, "metric": m, "year": y})
            for t, m, y in fact_cases
        ]

        timeseries_cases = [
            ("FPT", "net_revenue", 2021, 2025),
            ("FPT", "net_profit_yoy_growth", 2021, 2025),
            ("MBB", "net_interest_income", 2021, 2025),
        ]
        timeseries = [
            harness.execute_query("TIME_SERIES", {
                "ticker": t, "metric": m, "start_year": start, "end_year": end,
            })
            for t, m, start, end in timeseries_cases
        ]

        compares = [
            harness.execute_query("COMPARE", {
                "tickers": ["FPT", "HPG", "MWG"], "metric": "net_profit", "year": 2025,
            }),
            harness.execute_query("COMPARE", {
                "tickers": ["ACB", "MBB", "VCB"], "metric": "net_profit", "year": 2025,
            }),
        ]
        ranks = [
            harness.execute_query("RANK", {
                "metric": "net_profit", "year": 2025, "sector": "CORPORATE", "limit": 5,
            }),
            harness.execute_query("RANK", {
                "metric": "net_profit", "year": 2025, "sector": "BANK", "limit": 5,
            }),
        ]

        model_loaded_during_numerical_path = harness.tools._embedder is not None
        knowledge = [
            harness.execute_query("COMPANY_KNOWLEDGE", {
                "ticker": "FPT", "query": "mô hình kinh doanh", "top_k": 3,
            }),
            harness.execute_query("COMPANY_KNOWLEDGE", {
                "ticker": "ACB", "query": "ban lãnh đạo", "top_k": 3,
            }),
        ]
        guards = {
            "unknown_ticker": harness.execute_query("FACT", {
                "ticker": "XYZ_NOT_REAL", "metric": "net_profit", "year": 2025,
            }),
            "unsupported_sector_metric": harness.execute_query("FACT", {
                "ticker": "FPT", "metric": "roe", "year": 2025,
            }),
            "missing_year": harness.execute_query("FACT", {
                "ticker": "FPT", "metric": "net_profit", "year": 2017,
            }),
            "qdrant_numerical_concept": harness.execute_query("COMPANY_KNOWLEDGE", {
                "ticker": "FPT", "query": "net profit 2025", "top_k": 2,
            }),
        }

        facts_pass = all(item["status"] == "OK" and len(item["data"]) == 1 for item in facts)
        derived_pass = all(
            item["data"][0].get("metric_type") == "DERIVED"
            and item["data"][0].get("formula_version") == "v1"
            and item["data"][0].get("calculation_status") == "OK"
            for item in (facts[2], facts[3])
        )
        timeseries_pass = all(
            item["status"] == "OK"
            and len(item["data"]) == 5
            and [row["year"] for row in item["data"]] == list(range(2021, 2026))
            for item in timeseries
        )
        compare_pass = all(
            item["status"] == "OK" and len(item["data"]) == 3
            and len({row["ticker"] for row in item["data"]}) == 3
            for item in compares
        )
        rank_pass = all(
            item["status"] == "OK" and len(item["data"]) == 5
            and [row["value"] for row in item["data"]]
                == sorted([row["value"] for row in item["data"]], reverse=True)
            for item in ranks
        )
        knowledge_pass = all(
            item["status"] == "OK" and item["data"]
            and all(row["ticker"] == item["ticker"] for row in item["data"])
            and all("vector" not in row for row in item["data"])
            for item in knowledge
        )
        guards_pass = (
            guards["unknown_ticker"]["status"] == "INVALID_TICKER"
            and guards["unsupported_sector_metric"]["status"] == "UNSUPPORTED"
            and guards["missing_year"]["status"] == "MISSING"
            and guards["qdrant_numerical_concept"]["source"] == "QDRANT_QUALITATIVE"
            and "NUMERICAL_TRUTH_SOURCE=POSTGRESQL"
                in guards["qdrant_numerical_concept"]["warnings"]
        )
        contract_keys = {
            "tool", "status", "ticker", "tickers", "metric", "year", "period",
            "sector", "data", "source", "provenance", "errors", "warnings",
        }
        all_responses = facts + timeseries + compares + ranks + knowledge + list(guards.values())
        contract_pass = all(set(item) == contract_keys for item in all_responses)
        cross_source_guard_pass = (
            not model_loaded_during_numerical_path
            and all(item["source"].startswith("POSTGRESQL") for item in facts + timeseries + compares + ranks)
            and all(item["source"] == "QDRANT_QUALITATIVE" for item in knowledge)
        )
        passed = all([
            facts_pass, derived_pass, timeseries_pass, compare_pass, rank_pass,
            knowledge_pass, guards_pass, contract_pass, cross_source_guard_pass,
        ])

        summary = {
            "previous_step": "COMPANY_KNOWLEDGE_FULL_LOAD_PASS",
            "existing_query_code_reused": ["src.services.derived_metrics.calculate"],
            "query_tools": ["FACT", "TIME_SERIES", "COMPARE", "RANK", "COMPANY_KNOWLEDGE"],
            "result_contract_keys": sorted(contract_keys),
            "tests": {
                "facts": [compact(item) for item in facts],
                "timeseries": [compact(item) for item in timeseries],
                "compare": [compact(item) for item in compares],
                "rank": [compact(item) for item in ranks],
                "company_knowledge": [compact(item) for item in knowledge],
                "guards": {key: compact(value) for key, value in guards.items()},
            },
            "checks": {
                "fact": facts_pass,
                "derived_metric": derived_pass,
                "time_series": timeseries_pass,
                "compare": compare_pass,
                "rank": rank_pass,
                "company_knowledge": knowledge_pass,
                "ticker_sector_missing_guards": guards_pass,
                "stable_contract": contract_pass,
                "cross_source_guard": cross_source_guard_pass,
                "bge_m3_loaded_during_numerical_path": model_loaded_during_numerical_path,
            },
            "vnstock_called": False,
            "query_harness_mvp": "PASS" if passed else "FAIL",
            "ready_for_intent_router": "YES" if passed else "NO",
            "next_roadmap_phase": "Intent Router / Query Planner MVP" if passed else "Fix Query Harness MVP",
        }
        SUMMARY.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )

        lines = [
            "# Query Harness Core MVP", "",
            f"Validation: **{summary['query_harness_mvp']}**", "",
            "## Scope", "",
            "Deterministic FACT, TIME_SERIES, COMPARE, RANK and COMPANY_KNOWLEDGE tools. "
            "No Intent Router, LLM, UI, VNStock call, re-embedding or collection mutation.", "",
            "## Checks", "",
            "| Check | Result |", "|---|---|",
        ]
        lines.extend(
            f"| {name} | {'PASS' if value is False and name == 'bge_m3_loaded_during_numerical_path' else ('PASS' if value else 'FAIL')} |"
            for name, value in summary["checks"].items()
        )
        lines.extend([
            "", "## Guardrails", "",
            f"- Unknown ticker: `{guards['unknown_ticker']['status']}`.",
            f"- FPT + ROE: `{guards['unsupported_sector_metric']['status']}`.",
            f"- Missing 2017 fact: `{guards['missing_year']['status']}`.",
            "- Numerical truth remains PostgreSQL; Qdrant output is qualitative evidence only.",
            "- BGE-M3 remained unloaded for all numerical queries.",
            "- VNStock called: **NO**.", "",
            f"**QUERY_HARNESS_MVP = {summary['query_harness_mvp']}**", "",
            f"**READY_FOR_INTENT_ROUTER = {summary['ready_for_intent_router']}**", "",
            "STOP before Intent Router.",
        ])
        REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(json.dumps({
            "fact": facts_pass,
            "timeseries": timeseries_pass,
            "compare": compare_pass,
            "rank": rank_pass,
            "company_knowledge": knowledge_pass,
            "derived": derived_pass,
            "guards": guards_pass,
            "contract": contract_pass,
            "cross_source_guard": cross_source_guard_pass,
            "vnstock_called": False,
            "query_harness_mvp": summary["query_harness_mvp"],
        }, ensure_ascii=False))
        return 0 if passed else 1
    finally:
        harness.close()


if __name__ == "__main__":
    raise SystemExit(main())
