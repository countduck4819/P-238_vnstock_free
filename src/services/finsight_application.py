"""Application boundary around the validated FinSight chatbot pipeline."""
from __future__ import annotations

import os
from threading import Lock
from typing import Any

from src.services.financial_supervisor import FinancialAgentSupervisor
from src.services.llm_client import ExistingLangChainLLMClient, LLMClient
from src.services.query_harness import QueryHarness
from src.services.web_research import ControlledWebResearch, build_default_web_research


class FinSightApplication:
    """Own reusable backend resources and serialize access for the MVP runtime."""

    def __init__(
        self,
        *,
        harness: QueryHarness | None = None,
        llm_client: LLMClient | None = None,
        web_research: ControlledWebResearch | None = None,
    ) -> None:
        self.harness = harness or QueryHarness()
        self.llm_client = llm_client
        self.supervisor = FinancialAgentSupervisor(
            harness=self.harness, llm_client=self.llm_client, web_research=web_research,
        )
        # Backward-compatible attribute for callers that accessed the graph agent.
        self.agent = self.supervisor.agent
        self._lock = Lock()

    def answer(
        self, question: str, history: list[dict[str, str]] | None = None
    ) -> dict[str, Any]:
        with self._lock:
            return self.supervisor.answer(question, history)

    def close(self) -> None:
        self.supervisor.close()


def build_default_application() -> FinSightApplication:
    """Enable the existing LLM provider only through an explicit feature flag."""
    llm_client: LLMClient | None = None
    if os.environ.get("FINSIGHT_ENABLE_LLM", "false").strip().lower() == "true":
        llm_client = ExistingLangChainLLMClient()
    return FinSightApplication(
        llm_client=llm_client,
        web_research=build_default_web_research(),
    )
