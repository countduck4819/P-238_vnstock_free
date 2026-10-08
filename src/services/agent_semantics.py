"""General analytical-concept guidance for safe financial evidence selection."""
from __future__ import annotations

from src.services.intent_router import normalize_text
from src.services.query_tools import EVALUATION_METRICS

CONCEPT_CUES = {
    "profitability": (
        "kha nang sinh loi", "sinh loi", "loi nhuan", "profitability",
    ),
    "growth": ("tang truong", "phat trien", "tang hay giam", "growth"),
    "financial_health": (
        "suc khoe tai chinh", "tinh hinh tai chinh", "khoe len", "yeu di",
        "tai chinh toan dien",
    ),
    "efficiency": ("hieu qua", "roa", "roe", "bien loi nhuan", "efficiency"),
    "scale": ("quy mo", "tai san", "scale"),
    "leverage": ("ganh nang no", "don bay", "tong no", "no phai tra", "leverage"),
    "financial_statement_risk": (
        "rui ro tai chinh", "no vay", "no vay cao", "loi nhuan co rui ro",
        "rui ro loi nhuan", "rui ro no", "financial risk",
    ),
    "stability": ("on dinh", "bien dong", "nhat quan", "stability"),
    "current_events": (
        "gan day", "moi nhat", "su kien", "tin tuc", "trien vong",
        "thay doi", "anh huong", "hien tai",
    ),
}


def resolve_analytical_concepts(question: str) -> list[str]:
    text = normalize_text(question)
    concepts = [
        concept for concept, cues in CONCEPT_CUES.items()
        if any(cue in text for cue in cues)
    ]
    if "efficiency" in concepts and "scale" in concepts:
        concepts.insert(0, "efficiency_vs_scale")
    return list(dict.fromkeys(concepts))


def requires_external_research(question: str) -> bool:
    return "current_events" in resolve_analytical_concepts(question)


def metric_guidance(concepts: list[str], sector: str | None) -> list[str]:
    family = sector if sector in EVALUATION_METRICS else "CORPORATE"
    candidates: list[str] = []
    for concept in concepts:
        if concept == "profitability":
            candidates.extend(
                ["net_profit", "net_profit_yoy_growth", "roa", "roe"]
                if family == "BANK"
                else ["net_profit", "net_profit_yoy_growth", "net_profit_margin", "roa"]
            )
        elif concept == "growth":
            candidates.extend(
                ["net_profit", "net_profit_yoy_growth", "total_assets"]
                if family == "BANK"
                else ["net_revenue", "net_revenue_yoy_growth", "net_profit", "net_profit_yoy_growth"]
            )
        elif concept == "financial_health":
            candidates.extend(
                ["net_interest_income", "net_profit", "net_profit_yoy_growth", "roa", "roe", "total_assets", "total_equity"]
                if family == "BANK"
                else ["net_revenue", "net_revenue_yoy_growth", "net_profit", "net_profit_yoy_growth", "net_profit_margin", "total_assets", "total_liabilities"]
            )
        elif concept == "efficiency":
            candidates.extend(["roa", "roe"] if family == "BANK" else ["net_profit_margin", "roa"])
        elif concept == "scale":
            candidates.extend(["total_assets", "net_profit"])
        elif concept == "leverage":
            candidates.extend(
                ["total_assets", "total_equity"]
                if family == "BANK" else ["total_liabilities", "total_assets"]
            )
        elif concept == "financial_statement_risk":
            candidates.extend(
                ["total_assets", "total_equity", "net_profit", "net_profit_yoy_growth"]
                if family == "BANK"
                else ["total_liabilities", "total_assets", "net_profit", "net_profit_yoy_growth"]
            )
        elif concept == "stability":
            candidates.extend(["net_profit", "net_profit_yoy_growth", "roa"])
        elif concept == "efficiency_vs_scale":
            candidates.extend(["net_profit", "roa", "roe", "total_assets"])
    supported = set(EVALUATION_METRICS.get(family, ()))
    return [metric for metric in dict.fromkeys(candidates) if metric in supported]
