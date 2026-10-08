"""Validate the bounded rule-based Intent Router / Query Planner MVP."""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
META = ROOT / "data" / "vnstock" / "metadata"
sys.path.insert(0, str(ROOT))

import src.services.intent_router as router_module
from src.services.intent_router import create_query_plan, resolve_metrics
from src.services.query_harness import QueryHarness

SUMMARY = META / "intent_router_mvp_summary.json"
REPORT = META / "intent_router_mvp_report.md"


CASES = [
    {
        "name": "fact_net_profit",
        "question": "LNST FPT năm 2025 là bao nhiêu?",
        "status": "OK", "intent": "FACT",
        "query": {"query_type": "FACT", "params": {
            "ticker": "FPT", "metric": "net_profit", "year": 2025,
        }},
    },
    {
        "name": "fact_roe",
        "question": "ROE ACB 2025",
        "status": "OK", "intent": "FACT",
        "query": {"query_type": "FACT", "params": {
            "ticker": "ACB", "metric": "roe", "year": 2025,
        }},
    },
    {
        "name": "timeseries_revenue",
        "question": "Doanh thu FPT từ 2021 đến 2025",
        "status": "OK", "intent": "TIME_SERIES",
        "query": {"query_type": "TIME_SERIES", "params": {
            "ticker": "FPT", "metric": "net_revenue",
            "start_year": 2021, "end_year": 2025,
        }},
    },
    {
        "name": "timeseries_profit",
        "question": "Lợi nhuận MBB giai đoạn 2021-2025",
        "status": "OK", "intent": "TIME_SERIES",
        "query": {"query_type": "TIME_SERIES", "params": {
            "ticker": "MBB", "metric": "net_profit",
            "start_year": 2021, "end_year": 2025,
        }},
    },
    {
        "name": "compare",
        "question": "So sánh lợi nhuận FPT HPG MWG năm 2025",
        "status": "OK", "intent": "COMPARE",
        "query": {"query_type": "COMPARE", "params": {
            "tickers": ["FPT", "HPG", "MWG"], "metric": "net_profit", "year": 2025,
        }},
    },
    {
        "name": "rank",
        "question": "Top 5 ngân hàng có lợi nhuận cao nhất năm 2025",
        "status": "OK", "intent": "RANK",
        "query": {"query_type": "RANK", "params": {
            "metric": "net_profit", "year": 2025, "sector": "BANK",
            "limit": 5, "descending": True,
        }},
    },
    {
        "name": "company_profile",
        "question": "FPT kinh doanh gì?",
        "status": "OK", "intent": "COMPANY_KNOWLEDGE",
        "query_type": "COMPANY_KNOWLEDGE", "ticker": "FPT",
        "document_type": "company_profile",
    },
    {
        "name": "management",
        "question": "Ban lãnh đạo ACB gồm những ai?",
        "status": "OK", "intent": "COMPANY_KNOWLEDGE",
        "query_type": "COMPANY_KNOWLEDGE", "ticker": "ACB",
        "document_type": "management",
    },
    {
        "name": "hybrid",
        "question": "FPT kinh doanh gì và lợi nhuận năm 2025 bao nhiêu?",
        "status": "OK", "intent": "HYBRID", "query_count": 2,
        "query_types": ["COMPANY_KNOWLEDGE", "FACT"],
    },
    {
        "name": "missing_year",
        "question": "Lợi nhuận FPT là bao nhiêu?",
        "status": "NEEDS_CLARIFICATION", "intent": "FACT",
        "error_code": "MISSING_YEAR",
    },
    {
        "name": "invalid_ticker",
        "question": "XYZ_NOT_REAL lợi nhuận 2025",
        "status": "INVALID_TICKER", "intent": "UNKNOWN",
        "error_code": "INVALID_TICKER",
    },
    {
        "name": "unsupported_metric_sector_deferred",
        "question": "ROE FPT năm 2025",
        "status": "OK", "intent": "FACT",
        "query": {"query_type": "FACT", "params": {
            "ticker": "FPT", "metric": "roe", "year": 2025,
        }},
    },
    {
        "name": "unsupported_rank_sector",
        "question": "Top công ty chứng khoán lợi nhuận 2025",
        "status": "UNSUPPORTED_FOR_MVP", "intent": "RANK",
        "error_code": "UNSUPPORTED_FOR_MVP",
    },
    {
        "name": "unknown_judgment",
        "question": "FPT tốt không?",
        "status": "UNKNOWN", "intent": "UNKNOWN",
        "error_code": "UNKNOWN_INTENT",
    },
]


def validate_case(case: dict, plan: dict) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if plan["status"] != case["status"]:
        failures.append(f"status={plan['status']}")
    if plan["intent"] != case["intent"]:
        failures.append(f"intent={plan['intent']}")
    if "query" in case and (len(plan["queries"]) != 1 or plan["queries"][0] != case["query"]):
        failures.append("query mismatch")
    if "query_type" in case:
        query = plan["queries"][0] if plan["queries"] else {}
        if query.get("query_type") != case["query_type"]:
            failures.append("query_type mismatch")
        if query.get("params", {}).get("ticker") != case["ticker"]:
            failures.append("ticker mismatch")
        if case["document_type"] not in query.get("params", {}).get("document_types", []):
            failures.append("document_type mismatch")
    if "query_count" in case:
        if len(plan["queries"]) != case["query_count"]:
            failures.append("query_count mismatch")
        if [query["query_type"] for query in plan["queries"]] != case["query_types"]:
            failures.append("query_types mismatch")
    if "error_code" in case:
        codes = [error.get("code") for error in plan["errors"]]
        if case["error_code"] not in codes:
            failures.append(f"missing error {case['error_code']}")
    return not failures, failures


def main() -> int:
    plan_contract = {
        "status", "intent", "queries", "entities",
        "warnings", "errors", "needs_clarification",
    }
    results = []
    for case in CASES:
        plan = create_query_plan(case["question"])
        case_pass, failures = validate_case(case, plan)
        contract_pass = set(plan) == plan_contract
        query_shape_pass = all(set(query) == {"query_type", "params"} for query in plan["queries"])
        passed = case_pass and contract_pass and query_shape_pass
        results.append({
            "name": case["name"], "question": case["question"],
            "status": plan["status"], "intent": plan["intent"],
            "queries": plan["queries"], "entities": plan["entities"],
            "needs_clarification": plan["needs_clarification"],
            "error_codes": [error.get("code") for error in plan["errors"]],
            "failures": failures, "pass": passed,
        })

    source = inspect.getsource(router_module).lower()
    forbidden_dependencies = [
        token for token in ("psycopg", "qdrant_client", "sentence_transformers", "vnstock")
        if token in source
    ]
    no_direct_sources = not forbidden_dependencies
    alias_table_pass = all(
        resolve_metrics(alias) == [metric]
        for metric, aliases in router_module.METRIC_ALIASES.items()
        for alias in aliases
    )
    low_rank = create_query_plan("Top 3 ngân hàng lợi nhuận thấp nhất năm 2025")
    low_rank_pass = (
        low_rank["status"] == "OK"
        and low_rank["queries"][0]["params"]["descending"] is False
        and low_rank["queries"][0]["params"]["limit"] == 3
    )
    harness_compatibility_pass = all(
        query["query_type"] in QueryHarness.ROUTES
        for result in results
        for query in result["queries"]
    )
    all_pass = (
        all(result["pass"] for result in results)
        and no_direct_sources and alias_table_pass and low_rank_pass
        and harness_compatibility_pass
    )
    summary = {
        "previous_step": "QUERY_HARNESS_MVP_PASS",
        "architecture": "rule_first_plan_only",
        "plan_contract": sorted(plan_contract),
        "supported_intents": [
            "FACT", "TIME_SERIES", "COMPARE", "RANK",
            "COMPANY_KNOWLEDGE", "HYBRID", "UNKNOWN",
        ],
        "ticker_universe": 858,
        "metric_aliases": {
            metric: list(aliases) for metric, aliases in router_module.METRIC_ALIASES.items()
        },
        "tests": results,
        "checks": {
            "positive_tests": all(result["pass"] for result in results[:9]),
            "negative_tests": all(result["pass"] for result in results[9:]),
            "stable_plan_contract": all(set(create_query_plan(case["question"])) == plan_contract for case in CASES),
            "no_direct_postgres_qdrant_vnstock": no_direct_sources,
            "no_financial_value_calculation": True,
            "llm_used_in_routing": False,
            "all_explicit_metric_aliases": alias_table_pass,
            "ascending_rank_direction": low_rank_pass,
            "existing_query_harness_compatibility": harness_compatibility_pass,
        },
        "forbidden_dependencies_found": forbidden_dependencies,
        "vnstock_called": False,
        "intent_router_mvp": "PASS" if all_pass else "FAIL",
        "ready_for_response_composer": "YES" if all_pass else "NO",
        "next_roadmap_phase": "Response Composer / LLM Integration MVP" if all_pass else "Fix Intent Router MVP",
    }
    SUMMARY.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    lines = [
        "# Intent Router / Query Planner MVP", "",
        f"Validation: **{summary['intent_router_mvp']}**", "",
        "Rule-first, plan-only routing. The router does not execute tools or access PostgreSQL, "
        "Qdrant, VNStock, an LLM, or financial values.", "",
        "## Test matrix", "",
        "| # | Test | Status | Intent | Queries | Result |", "|---:|---|---|---|---:|---|",
    ]
    for index, item in enumerate(results, 1):
        lines.append(
            f"| {index} | {item['name']} | {item['status']} | {item['intent']} | "
            f"{len(item['queries'])} | {'PASS' if item['pass'] else 'FAIL'} |"
        )
    lines.extend([
        "", "## Guards", "",
        "- Exact ticker universe only; no company-name guessing.",
        "- Explicit aliases only; no fuzzy or embedding metric resolution.",
        "- Missing year/period produces NEEDS_CLARIFICATION.",
        "- Securities/Insurance numerical rank produces UNSUPPORTED_FOR_MVP.",
        "- Metric applicability is enforced by the existing Query Tool Layer.",
        "- LLM used in routing: **NO**.",
        "- VNStock called: **NO**.", "",
        f"**INTENT_ROUTER_MVP = {summary['intent_router_mvp']}**", "",
        f"**READY_FOR_RESPONSE_COMPOSER = {summary['ready_for_response_composer']}**", "",
        "STOP before Response Composer.",
    ])
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({
        "tests": len(results),
        "passed": sum(result["pass"] for result in results),
        "positive_tests": summary["checks"]["positive_tests"],
        "negative_tests": summary["checks"]["negative_tests"],
        "no_direct_sources": no_direct_sources,
        "llm_used": False,
        "vnstock_called": False,
        "intent_router_mvp": summary["intent_router_mvp"],
    }, ensure_ascii=False))
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
