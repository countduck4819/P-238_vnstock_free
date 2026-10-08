"""Small supervisor boundary for the FinSight financial research agent.

This is a routing facade, not another LangGraph node.  It delegates complex
questions to the existing bounded graph and simple deterministic questions to
the existing query pipeline, while sharing one harness and one evidence path.
"""
from __future__ import annotations

import os
from threading import Lock
from typing import Any

from src.services.agent_planner import should_use_agent
from src.services.chat_pipeline import answer_question, contextualize_question
from src.services.financial_agent import FinancialResearchAgent
from src.services.financial_decision_layer import FinancialAnalystDecisionLayer
from src.services.intent_router import resolve_tickers
from src.services.llm_client import ExistingLangChainLLMClient, LLMClient
from src.services.query_harness import QueryHarness
from src.services.web_research import ControlledWebResearch, build_default_web_research


class UnifiedFinancialQueryHandler:
    """Route every natural-language request through one public handler."""

    def __init__(
        self,
        *,
        harness: QueryHarness | None = None,
        llm_client: LLMClient | None = None,
        web_research: ControlledWebResearch | None = None,
    ) -> None:
        self.harness = harness or QueryHarness()
        self.llm_client = llm_client
        self.agent = FinancialResearchAgent(
            self.harness, llm_client=llm_client, web_research=web_research,
        )
        self.decision_layer = FinancialAnalystDecisionLayer()
        self._lock = Lock()

    def answer(self, question: Any, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
        with self._lock:
            text = str(question or "")
            effective_text, context_applied = contextualize_question(text, history)
            decision = self.decision_layer.classify(effective_text)
            if decision.intent == "VALUATION_ANALYSIS":
                response = {
                    "status": "UNKNOWN",
                    "answer": (
                        "<section><h3>Kết luận</h3>"
                        "<p>Chưa đủ dữ liệu để đánh giá định giá của mã cổ phiếu này.</p></section>"
                        "<section><h3>Dữ liệu cần có</h3><ul>"
                        "<li>Giá thị trường</li><li>P/E</li><li>P/B</li><li>EPS</li><li>Vốn hóa</li>"
                        "</ul></section>"
                    ),
                    "intent": decision.intent,
                    "sources": [], "warnings": ["VALUATION_EVIDENCE_MISSING"],
                    "errors": [], "data_used": [], "mode": "DECISION_LAYER",
                    "llm_used": False,
                }
                result = {
                    "question": text, "effective_question": text,
                    "context_applied": False,
                    "plan": {"status": "OK", "intent": decision.intent,
                             "entities": {"tickers": resolve_tickers(text)[0], "metrics": [], "years": [], "sector": None},
                             "queries": []},
                    "results": [], "response": response,
                }
                result["supervisor"] = {"route": "DECISION_LAYER", "evidence_grounded": True}
                return result
            use_agent = should_use_agent(effective_text)
            if use_agent:
                response = self.agent.answer(effective_text)
            else:
                response = answer_question(
                    effective_text, history=None, harness=self.harness, llm_client=self.llm_client,
                )
            response["question"] = text
            response["effective_question"] = effective_text
            response["context_applied"] = context_applied
            response.setdefault("supervisor", {})
            response["supervisor"].update({
                "route": "LANGGRAPH_AGENT" if use_agent else "DETERMINISTIC_QUERY",
                "evidence_grounded": True,
            })
            return response

    def close(self) -> None:
        self.harness.close()


class FinancialAgentSupervisor(UnifiedFinancialQueryHandler):
    """Named architecture boundary for dependency injection and deployment."""


def build_default_supervisor() -> FinancialAgentSupervisor:
    llm_client: LLMClient | None = None
    if os.environ.get("FINSIGHT_ENABLE_LLM", "false").strip().lower() == "true":
        llm_client = ExistingLangChainLLMClient()
    return FinancialAgentSupervisor(
        llm_client=llm_client, web_research=build_default_web_research(),
    )


__all__ = ["FinancialAgentSupervisor", "UnifiedFinancialQueryHandler", "build_default_supervisor"]
