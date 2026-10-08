"""Public boundary for the LangGraph Financial Research Agent MVP."""
from __future__ import annotations

from typing import Any

from src.services.agent_budget import AgentBudget
from src.services.agent_graph import FinancialAgentGraph
from src.services.agent_planner import StructuredAgentPlanner, should_use_agent
from src.services.financial_decision_layer import FinancialAnalystDecisionLayer
from src.services.llm_client import LLMClient
from src.services.query_harness import QueryHarness
from src.services.web_research import ControlledWebResearch


class FinancialResearchAgent:
    def __init__(
        self, harness: QueryHarness, *, llm_client: LLMClient | None = None,
        max_iterations: int | None = None,
        max_llm_calls: int | None = None,
        max_tool_calls: int | None = None,
        max_replans: int | None = None,
        max_web_calls: int | None = None,
        max_web_sources: int | None = None,
        max_external_content: int | None = None,
        web_research: ControlledWebResearch | None = None,
    ) -> None:
        configured = AgentBudget.from_env()
        budget = AgentBudget(
            max_iterations=max_iterations or configured.max_iterations,
            max_llm_calls=max_llm_calls or configured.max_llm_calls,
            max_tool_calls=max_tool_calls or configured.max_tool_calls,
            max_replans=max_replans or configured.max_replans,
            max_web_calls=max_web_calls or configured.max_web_calls,
            max_web_sources=max_web_sources or configured.max_web_sources,
            max_external_content=max_external_content or configured.max_external_content,
        ).bounded()
        self.runner = FinancialAgentGraph(
            harness,
            StructuredAgentPlanner(llm_client),
            budget=budget,
            web_research=web_research,
        )
        self.decision_layer = FinancialAnalystDecisionLayer()

    def answer(self, question: Any) -> dict[str, Any]:
        state = self.runner.invoke(str(question))
        analyst_decision = self.decision_layer.classify(question)
        enhanced_answer = self.decision_layer.enhance(
            question, state, state.get("final_answer") or ""
        )
        status = state.get("status", "FAILED")
        public_status = "OK" if status == "COMPLETED" else status
        public_intent = (
            analyst_decision.intent
            if analyst_decision.intent in {"FINANCIAL_STATEMENT_RISK", "RECENT_EVENT_RISK"}
            else "FINANCIAL_RESEARCH_AGENT"
        )
        if analyst_decision.intent == "RECENT_EVENT_RISK" and not state.get("web_sources"):
            public_status = "UNKNOWN"
            enhanced_answer = "Dữ liệu hiện tại chưa đủ để trả lời"
        return {
            "question": str(question),
            "effective_question": str(question),
            "context_applied": False,
            "plan": {
                "status": status,
                "intent": public_intent,
                "goal": state.get("goal"),
                "entities": {
                    "tickers": state.get("tickers") or [],
                    "sector": state.get("sector"),
                    "period": state.get("period") or {},
                },
                "queries": [
                    {"query_type": call["query_type"], "params": call["params"]}
                    for call in state.get("tool_calls") or []
                ],
                "iteration_count": state.get("iteration_count", 0),
                "max_iterations": state.get("max_iterations", 10),
                "tool_call_count": state.get("tool_call_count", 0),
                "max_tool_calls": state.get("max_tool_calls", 10),
                "replan_count": state.get("replan_count", 0),
                "max_replans": state.get("max_replans", 3),
                "web_call_count": state.get("web_call_count", 0),
                "max_web_calls": state.get("max_web_calls", 4),
                "missing_information": state.get("missing_information") or [],
            },
            "results": state.get("results") or [],
            "agent_trace": state.get("trace") or [],
            "response": {
                "status": public_status,
                "answer": enhanced_answer,
                "intent": public_intent,
                "sources": [
                    {"type": observation.source}
                    for observation in state.get("observations") or []
                    if observation.source
                ],
                "warnings": state.get("warnings") or [],
                "errors": [],
                "data_used": state.get("evidence") or [],
                "web_sources": state.get("web_sources") or [],
                "source_conflicts": state.get("source_conflicts") or [],
                "research_complete": bool(state.get("research_complete")),
                "mode": "LANGGRAPH_LLM_AGENT" if state.get("llm_call_count") else "LANGGRAPH_SAFE_FALLBACK",
                "llm_used": bool(state.get("llm_call_count")),
                "llm_call_count": state.get("llm_call_count", 0),
            },
        }


__all__ = ["FinancialResearchAgent", "should_use_agent"]
