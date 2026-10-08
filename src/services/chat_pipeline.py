"""Thin end-to-end backend pipeline; not a server and not an agent loop."""
from __future__ import annotations

import re
from typing import Any

from src.services.intent_router import (
    create_query_plan,
    normalize_text,
    resolve_knowledge_types,
)
from src.services.llm_client import LLMClient
from src.services.query_harness import QueryHarness
from src.services.response_composer import compose_response


def execute_plan(plan: dict, harness: QueryHarness) -> list[dict]:
    """Execute already-structured queries without natural-language reasoning."""
    if plan.get("status") != "OK":
        return []
    return [
        harness.execute_query(query["query_type"], query["params"])
        for query in plan.get("queries", [])
    ]


def _first_entity(plans: list[tuple[str, dict]], key: str) -> Any:
    for _, plan in plans:
        value = plan.get("entities", {}).get(key)
        if isinstance(value, list) and value:
            return value
        if value not in (None, "") and not isinstance(value, list):
            return value
    return [] if key != "sector" else None


def _rank_limit_and_direction(current_text: str, source_text: str) -> tuple[int, str]:
    limit = 10
    for text in (current_text, source_text):
        normalized = normalize_text(text)
        match = re.search(
            r"(?<!\w)(?:top|bottom|rank|xep hang)\s*(\d+)(?!\w)", normalized
        ) or re.search(
            r"(?<!\w)(\d{1,3})\s+(?:doanh nghiep|ngan hang|ma co phieu|co phieu)(?!\w)",
            normalized,
        )
        if match:
            limit = int(match.group(1))
            break
    normalized = normalize_text(f"{source_text} {current_text}")
    descending = not any(
        cue in normalized for cue in ("bottom", "lowest", "thap nhat", "nho nhat")
    )
    return limit, "highest" if descending else "lowest"


def contextualize_question(
    question: Any, history: list[dict[str, str]] | None
) -> tuple[str, bool]:
    """Fill omitted follow-up slots from recent user turns.

    History is used only to reconstruct query parameters. Financial answers are
    still fetched again from PostgreSQL/Qdrant and are never copied from memory.
    """
    current = str(question or "").strip()
    current_plan = create_query_plan(current)
    if any(
        error.get("code") == "GIBBERISH_OR_UNSUPPORTED"
        for error in current_plan.get("errors", [])
    ):
        return current, False
    if not history or current_plan.get("status") == "OK":
        return current, False

    current_intent = current_plan.get("intent")
    current_entities = current_plan.get("entities", {})
    contextual_intents = {
        "RANK", "COMPARE", "TIME_SERIES", "COMPANY_KNOWLEDGE", "HYBRID",
        "EVALUATION",
    }
    # An explicit new analytical request starts a new context and should ask for
    # its own missing slots instead of silently borrowing them from an old topic.
    if current_intent in contextual_intents:
        return current, False
    # A FACT containing both ticker and metric is also a complete new topic. It
    # may still ask for a year, but must not inherit an old ranking sector/intent.
    if (
        current_intent == "FACT"
        and current_entities.get("tickers")
        and current_entities.get("metrics")
    ):
        return current, False

    prior_questions = [
        str(message.get("content", "")).strip()
        for message in reversed(history)
        if message.get("role") == "user" and str(message.get("content", "")).strip()
    ]
    if not prior_questions:
        return current, False

    candidates = [(current, current_plan)] + [
        (text, create_query_plan(text)) for text in prior_questions[:6]
    ]
    intent_source = None
    for text, plan in candidates[1:]:
        intent = plan.get("intent")
        entities = plan.get("entities", {})
        if intent in contextual_intents:
            intent_source = (text, plan)
            break
        if intent == "FACT" and entities.get("tickers") and entities.get("metrics"):
            intent_source = (text, plan)
            break
    if intent_source is None:
        return current, False

    source_text, source_plan = intent_source
    intent = source_plan.get("intent")
    tickers = _first_entity(candidates, "tickers")
    metrics = _first_entity(candidates, "metrics")
    years = _first_entity(candidates, "years")
    sector = _first_entity(candidates, "sector")
    ticker_text = " ".join(tickers)
    metric_text = metrics[0] if metrics else ""
    year_text = " ".join(str(year) for year in years)

    if intent == "RANK":
        limit, direction = _rank_limit_and_direction(current, source_text)
        effective = f"rank {limit} {sector or ''} by {metric_text} {year_text} {direction}"
    elif intent == "COMPARE":
        effective = f"so sánh {ticker_text} {metric_text} {year_text}"
    elif intent == "TIME_SERIES":
        effective = f"xu hướng {ticker_text} {metric_text} {year_text}"
    elif intent == "EVALUATION":
        effective = f"đánh giá cổ phiếu {ticker_text} {year_text}"
    elif intent in {"COMPANY_KNOWLEDGE", "HYBRID"}:
        knowledge_type = next(
            (
                document_type
                for text, _ in candidates
                for document_type in resolve_knowledge_types(text)
            ),
            "company_profile",
        )
        knowledge_cue = {
            "company_profile": "kinh doanh gì",
            "company_history": "lịch sử",
            "management": "ban lãnh đạo",
            "listing_info": "thông tin niêm yết",
        }[knowledge_type]
        effective = f"{ticker_text} {knowledge_cue} {metric_text} {year_text}"
    else:
        effective = f"{ticker_text} {metric_text} {year_text}"

    effective = " ".join(effective.split())
    return (effective, effective != current)


def answer_question(
    question: Any,
    *,
    history: list[dict[str, str]] | None = None,
    harness: QueryHarness | None = None,
    llm_client: LLMClient | None = None,
) -> dict:
    """Route, execute deterministic tools, then compose a structured response."""
    owned_harness = harness is None
    active_harness = harness or QueryHarness()
    try:
        effective_question, context_applied = contextualize_question(question, history)
        plan = create_query_plan(effective_question)
        results = execute_plan(plan, active_harness)
        response = compose_response(effective_question, plan, results, llm_client)
        return {
            "question": str(question),
            "effective_question": effective_question,
            "context_applied": context_applied,
            "plan": plan,
            "results": results,
            "response": response,
        }
    finally:
        if owned_harness:
            active_harness.close()
