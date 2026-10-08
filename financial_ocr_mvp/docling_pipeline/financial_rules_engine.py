"""Validate semantic financial facts without changing source data."""
from __future__ import annotations

import argparse
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

NUMBER = re.compile(r"^\(?[0-9]{1,3}(?:\.[0-9]{3})*\)?$")


def parse_number(value: Any) -> Decimal | None:
    text = str(value or "").strip()
    if not NUMBER.fullmatch(text):
        return None
    negative = text.startswith("(")
    text = text.strip("()").replace(".", "")
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    return -value if negative else value


def fact_location(fact: dict[str, Any]) -> tuple[str, int]:
    source = fact.get("source", {})
    table = str(source.get("table", ""))
    column = fact.get("column", {})
    if isinstance(column, dict):
        column_index = column.get("index", source.get("column", -1))
    else:
        column_index = column
    try:
        return table, int(column_index)
    except (TypeError, ValueError):
        return table, -1


def fact_trace(fact: dict[str, Any]) -> dict[str, Any]:
    return {
        "concept": fact.get("concept"),
        "value": fact.get("final_value", fact.get("value", "")),
        "source": fact.get("source", {}),
    }


def run_rule(rule: str, concepts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    formulas = {
        "gross_profit": ("revenue_minus_cost_of_goods_sold", ("revenue", "cost_of_goods_sold", "gross_profit")),
        "profit_before_tax": ("operating_plus_other_plus_associates_profit", ("operating_profit", "other_profit", "associates_profit", "profit_before_tax")),
        "net_income": ("profit_before_tax_minus_tax_expense", ("profit_before_tax", "current_income_tax_expense", "deferred_income_tax_expense", "net_income")),
        "balance_sheet": ("total_assets_equals_liabilities_plus_equity", ("total_assets", "liabilities", "equity")),
    }
    formula, required = formulas[rule]
    used = [concepts.get(concept) for concept in required]
    used_facts = [fact_trace(fact) for fact in used if fact is not None]
    if any(fact is None for fact in used):
        return {"rule": rule, "formula": formula, "status": "not_applicable", "expected": None, "actual": None, "facts_used": used_facts, "reason": "required_concept_missing"}

    values = {concept: parse_number(fact.get("final_value", fact.get("value"))) for concept, fact in zip(required, used)}
    if any(value is None for value in values.values()):
        return {"rule": rule, "formula": formula, "status": "not_applicable", "expected": None, "actual": None, "facts_used": used_facts, "reason": "required_value_not_numeric"}

    if rule == "gross_profit":
        expected = values["revenue"] - values["cost_of_goods_sold"]
        actual = values["gross_profit"]
    elif rule == "profit_before_tax":
        expected = values["operating_profit"] + values["other_profit"] + values["associates_profit"]
        actual = values["profit_before_tax"]
    elif rule == "net_income":
        expected = values["profit_before_tax"] - values["current_income_tax_expense"] - values["deferred_income_tax_expense"]
        actual = values["net_income"]
    else:
        expected = values["liabilities"] + values["equity"]
        actual = values["total_assets"]

    return {
        "rule": rule,
        "formula": formula,
        "status": "pass" if expected == actual else "fail",
        "expected": str(expected),
        "actual": str(actual),
        "facts_used": used_facts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run semantic financial accounting rules")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    document = json.loads(args.input.read_text(encoding="utf-8"))
    groups: dict[tuple[str, int], dict[str, dict[str, Any]]] = {}
    for fact in document.get("facts", []):
        concept = fact.get("concept")
        if not concept or concept == "unknown":
            continue
        groups.setdefault(fact_location(fact), {}).setdefault(concept, fact)

    rules: list[dict[str, Any]] = []
    rule_names = ["gross_profit", "profit_before_tax", "net_income", "balance_sheet"]
    for (table, column), concepts in sorted(groups.items()):
        for rule_name in rule_names:
            result = run_rule(rule_name, concepts)
            result.update({"table": table, "column": column})
            rules.append(result)

    summary = {
        "total_rules": len(rules),
        "pass": sum(item["status"] == "pass" for item in rules),
        "fail": sum(item["status"] == "fail" for item in rules),
        "not_applicable": sum(item["status"] == "not_applicable" for item in rules),
    }
    output = {
        "schema": "financial_validation_rules_v1",
        "source": str(args.input),
        "summary": summary,
        "rules": rules,
        "policy": {
            "data_mutation": False,
            "raw_value_overwrite": False,
            "numeric_normalization": False,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Saved:", args.output)
    print(summary)


if __name__ == "__main__":
    main()
