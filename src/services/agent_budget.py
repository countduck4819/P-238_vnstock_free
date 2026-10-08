"""Hard per-request budgets for bounded agent execution."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _bounded_env(name: str, default: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, default))
    except (TypeError, ValueError):
        value = default
    return min(max(1, value), maximum)


@dataclass(frozen=True)
class AgentBudget:
    max_iterations: int = 10
    max_llm_calls: int = 5
    max_tool_calls: int = 10
    max_replans: int = 3
    max_web_calls: int = 4
    max_web_sources: int = 10
    max_external_content: int = 12_000

    @classmethod
    def from_env(cls) -> AgentBudget:
        return cls(
            max_iterations=_bounded_env("MAX_AGENT_ITERATIONS", 10, 10),
            max_llm_calls=_bounded_env("MAX_LLM_CALLS_PER_REQUEST", 5, 10),
            max_tool_calls=_bounded_env("MAX_TOOL_CALLS_PER_REQUEST", 10, 20),
            max_replans=_bounded_env("MAX_REPLANS_PER_REQUEST", 3, 5),
            max_web_calls=_bounded_env("MAX_WEB_SEARCH_CALLS_PER_REQUEST", 4, 4),
            max_web_sources=_bounded_env("MAX_WEB_SOURCES_PER_REQUEST", 10, 10),
            max_external_content=_bounded_env("MAX_TOTAL_EXTERNAL_CONTENT", 12_000, 30_000),
        )

    def bounded(self) -> AgentBudget:
        return AgentBudget(
            max_iterations=min(max(1, self.max_iterations), 10),
            max_llm_calls=min(max(1, self.max_llm_calls), 10),
            max_tool_calls=min(max(1, self.max_tool_calls), 20),
            max_replans=min(max(1, self.max_replans), 5),
            max_web_calls=min(max(1, self.max_web_calls), 4),
            max_web_sources=min(max(1, self.max_web_sources), 10),
            max_external_content=min(max(1000, self.max_external_content), 30_000),
        )
