"""Thin deterministic Query Harness Core MVP (no natural-language routing)."""
from __future__ import annotations

from typing import Any

from src.services.agent_actions import TOOL_REGISTRY
from src.services.query_tools import QueryTools, result


class QueryHarness:
    ROUTES = {key: value for key, value in TOOL_REGISTRY.items() if key != "WEB_SEARCH"}

    def check_availability(self, query_type: Any) -> tuple[bool, str | None]:
        """Validate registry availability without performing I/O."""
        normalized = str(query_type or "").strip().upper()
        if normalized == "WEB_SEARCH":
            return False, "WEB_SEARCH_IS_OWNED_BY_CONTROLLED_WEB_RESEARCH"
        if normalized not in self.ROUTES:
            return False, "TOOL_NOT_REGISTERED"
        return hasattr(self.tools, self.ROUTES[normalized]), None

    def __init__(self, tools: QueryTools | None = None) -> None:
        self.tools = tools or QueryTools()

    def close(self) -> None:
        self.tools.close()

    def execute_query(self, query_type: Any, params: Any) -> dict:
        normalized_type = str(query_type or "").strip().upper()
        available, reason = self.check_availability(normalized_type)
        if not available:
            return result(
                normalized_type.lower(), "TOOL_UNAVAILABLE",
                errors=[{"code": "TOOL_UNAVAILABLE", "message": reason or "Tool unavailable"}],
            )
        method_name = self.ROUTES.get(normalized_type)
        if method_name is None:
            return result(
                "execute_query", "UNSUPPORTED",
                errors=[{"code": "UNSUPPORTED", "message": f"Unsupported query_type: {normalized_type}"}],
            )
        if not isinstance(params, dict):
            return result(
                method_name, "INVALID_PARAMETERS",
                errors=[{"code": "INVALID_PARAMETERS", "message": "params must be an object"}],
            )
        try:
            return getattr(self.tools, method_name)(**params)
        except TypeError as exc:
            return result(
                method_name, "INVALID_PARAMETERS",
                errors=[{"code": "INVALID_PARAMETERS", "message": str(exc)}],
            )


def execute_query(query_type: Any, params: Any, tools: QueryTools | None = None) -> dict:
    """Convenience entry point; pass a shared QueryTools instance for connection/model reuse."""
    harness = QueryHarness(tools)
    if tools is not None:
        return harness.execute_query(query_type, params)
    try:
        return harness.execute_query(query_type, params)
    finally:
        harness.close()
