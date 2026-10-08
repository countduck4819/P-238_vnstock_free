"""Minimal provider abstraction for optional response composition."""
from __future__ import annotations

from typing import Protocol


class LLMClient(Protocol):
    def generate(self, system_prompt: str, user_prompt: str) -> str: ...


class ExistingLangChainLLMClient:
    """Adapter around the project's existing ChatOpenAI configuration."""

    def __init__(self) -> None:
        from src.services.llm import get_llm

        self._client = get_llm()

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        response = self._client.invoke([
            ("system", system_prompt),
            ("user", user_prompt),
        ])
        return str(response.content).strip()
