"""Map Vietnamese financial metrics to stable semantic concepts.

This module changes only semantic metadata. All OCR evidence and values remain
unchanged and auditable.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import unicodedata
from pathlib import Path
from typing import Any


def normalize_label(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("đ", "d")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", text)).strip()


# Ordered from specific to general to avoid mapping child rows to a parent metric.
RULES = [
    (("loi nhuan sau thue cua co dong cua cong ty me", "loi nhuan sau thue cua co dong cong ty me", "loi nhuin sau thue cua co dong", "loi nhuin sau thue cua co dang"), "parent_company_net_income", "income_statement", "profit"),
    (("loi ich cua co dong thieu so", "loi ich co dong thieu so", "lot tch cua co dong thieu so", "lot tch cua co dong thteu so"), "minority_interest", "income_statement", "equity"),
    (("loi nhuan sau thue thu nhap doanh nghiep", "loi nhuan sau thue", "lqi nhusn sau thue"), "net_income", "income_statement", "profit"),
    (("loi nhuan truoc thue", "tong loi nhuan ke toan truoc thue"), "profit_before_tax", "income_statement", "profit"),
    (("loi nhuan thuan tu hoat dong kinh doanh", "loi nhuan hoat dong", "lqi nhun thuan"), "operating_profit", "income_statement", "profit"),
    (("loi nhuan gop", "loi nhuan gp", "lqi nhuzn gp"), "gross_profit", "income_statement", "profit"),
    (("loi nhuan khac", "lqi nhuan khac", "lai nhuln khac"), "other_profit", "income_statement", "profit"),
    (("doanh thu hoat dong tai chinh", "doanh thu hopt dong tai chinh"), "financial_income", "income_statement", "revenue"),
    (("doanh thu ve ban hang", "doanh thu ban hang", "doanh thu thuan", "dounh thu kinh doanh", "doanh thu thun ban"), "revenue", "income_statement", "revenue"),
    (("gia von hang ban",), "cost_of_goods_sold", "income_statement", "expense"),
    (("chi phi tai chinh",), "financial_expense", "income_statement", "expense"),
    (("chi phi lai vay",), "interest_expense", "income_statement", "expense"),
    (("chi phi ban hang",), "selling_expense", "income_statement", "expense"),
    (("chi phi quan ly doanh nghiep",), "general_and_administrative_expense", "income_statement", "expense"),
    (("thu nhap khac",), "other_income", "income_statement", "revenue"),
    (("chi phi khac",), "other_expense", "income_statement", "expense"),
    (("loi nhuan tu cong ty lien doanh", "loi nhuan tu cong ty lien ket", "lai nhugn tur cong ty lien doanh"), "associates_profit", "income_statement", "profit"),
    (("truoe trich quy", "truoc trich quy"), "profit_before_development_fund", "income_statement", "profit"),
    (("quy dau tu phat trien",), "development_fund", "income_statement", "equity"),
    (("sau trich quy",), "profit_after_development_fund", "income_statement", "profit"),
    (("chi phi thue tndn hien hanh", "thue tndn hien hanh"), "current_income_tax_expense", "income_statement", "expense"),
    (("chi phi thue tndn hoan lai", "thue tndn hoan lai", "d hlai"), "deferred_income_tax_expense", "income_statement", "expense"),
    (("tong tai san",), "total_assets", "balance_sheet", "asset"),
    (("tai san ngan han",), "current_assets", "balance_sheet", "asset"),
    (("tai san dai han",), "non_current_assets", "balance_sheet", "asset"),
    (("tong nguon von", "tong cong nguon von"), "total_equity_and_liabilities", "balance_sheet", "liability"),
    (("no phai tra", "tong no phai tra"), "liabilities", "balance_sheet", "liability"),
    (("no ngan han",), "current_liabilities", "balance_sheet", "liability"),
    (("no dai han",), "non_current_liabilities", "balance_sheet", "liability"),
    (("von chu so huu",), "equity", "balance_sheet", "equity"),
    (("tien va cac khoan tuong duong tien",), "cash_and_cash_equivalents", "balance_sheet", "asset"),
    (("lai co ban tren co phieu", "lai co ban tren c phiu"), "basic_earnings_per_share", "income_statement", "profit"),
    (("luu chuyen tien te tu hoat dong kinh doanh",), "operating_cash_flow", "cash_flow", "cash_flow"),
    (("luu chuyen tien te tu hoat dong dau tu",), "investing_cash_flow", "cash_flow", "cash_flow"),
    (("luu chuyen tien te tu hoat dong tai chinh",), "financing_cash_flow", "cash_flow", "cash_flow"),
    (("luu chuyen tien thuan trong ky", "luu chuyen tien thuan"), "net_change_in_cash", "cash_flow", "cash_flow"),
]

NORMALIZED_RULES = [([normalize_label(alias) for alias in aliases], concept, statement, category) for aliases, concept, statement, category in RULES]


def map_metric(metric: str) -> tuple[str, str, str, str]:
    label = normalize_label(metric)
    for aliases, concept, statement_type, category in NORMALIZED_RULES:
        if any(alias in label for alias in aliases):
            return concept, statement_type, category, "deterministic_alias_match"
    return "unknown", "unknown", "unknown", "no_safe_metric_match"


def main() -> None:
    parser = argparse.ArgumentParser(description="Map financial facts to semantic concepts")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    document = json.loads(args.input.read_text(encoding="utf-8"))
    facts = []
    counts = {"mapped": 0, "unknown": 0, "needs_review": 0}

    for original in document.get("facts", []):
        fact = copy.deepcopy(original)
        concept, statement_type, category, reason = map_metric(fact.get("metric", ""))
        fact["concept"] = concept
        fact["statement_type"] = statement_type
        fact["financial_category"] = category
        fact["semantic_mapping"] = {
            "status": "mapped" if concept != "unknown" else "needs_review",
            "method": "deterministic_alias_match",
            "reason": reason,
        }
        if concept == "unknown":
            counts["unknown"] += 1
            counts["needs_review"] += 1
        else:
            counts["mapped"] += 1
        facts.append(fact)

    output = {
        "schema": "financial_fact_v2",
        "status": "needs_review" if counts["needs_review"] else "ready",
        "summary": {
            "total_facts": len(facts),
            **counts,
            "raw_values_overwritten": 0,
        },
        "facts": facts,
        "provenance": {
            "input": str(args.input),
            "method": "deterministic Vietnamese financial metric mapper",
        },
        "policy": {
            "raw_value_overwrite": False,
            "numeric_normalization": False,
            "unknown_metrics_are_reviewed": True,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Saved:", args.output)
    print(output["summary"])


if __name__ == "__main__":
    main()
