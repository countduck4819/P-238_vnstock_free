"""Evidence and stop-condition checks for the bounded agent loop."""
from __future__ import annotations

from typing import Any

from src.services.agent_state import AgentState, Observation

NUMERICAL_TOOLS = {"get_fact", "get_timeseries", "compare", "rank", "evaluate_stock"}


class AgentCritic:
    def validate_claim(self, claim: dict[str, Any], state: AgentState) -> tuple[bool, str | None]:
        """Validate a proposed numerical claim against an observed backend row."""
        if claim.get("value") is None:
            return False, "A numerical claim cannot use a missing value."
        metric = claim.get("metric")
        ticker = claim.get("ticker")
        year = claim.get("year")
        for observation in state.observations:
            if observation.tool not in NUMERICAL_TOOLS or observation.source not in {None, "POSTGRESQL", "DERIVED"}:
                continue
            for row in observation.data:
                if (
                    row.get("canonical_metric_code", row.get("metric")) == metric
                    and (ticker is None or row.get("ticker") == ticker)
                    and (year is None or row.get("year") == year)
                    and row.get("status", "OK") == "OK"
                    and row.get("value") is not None
                ):
                    return True, None
        return False, "Numerical claim has no matching PostgreSQL/derived evidence."

    def validate_observation(self, observation: Observation) -> tuple[bool, str | None]:
        if observation.status in {"UNSUPPORTED", "UNSUPPORTED_FOR_MVP", "MISSING_INPUT", "ZERO_DENOMINATOR", "INVALID_TICKER", "NEEDS_CLARIFICATION"}:
            return True, None
        if observation.tool in NUMERICAL_TOOLS:
            for row in observation.data:
                if row.get("value") is not None and row.get("status") not in (None, "OK"):
                    return False, "Numerical observation contains a value with a non-OK status."
                if row.get("value") is not None and observation.source not in {None, "POSTGRESQL", "DERIVED"}:
                    return False, "Numerical claims must come from PostgreSQL or derived backend."
        if observation.tool == "search_company_knowledge" and observation.source == "POSTGRESQL":
            return False, "Qualitative Qdrant evidence cannot be relabeled as PostgreSQL."
        return True, None

    def validate(self, state: AgentState) -> tuple[bool, list[str]]:
        return self.validate_observations(state.observations)

    def validate_observations(
        self, observations: list[Observation]
    ) -> tuple[bool, list[str]]:
        failures: list[str] = []
        for observation in observations:
            valid, reason = self.validate_observation(observation)
            if not valid and reason:
                failures.append(reason)
        return not failures, failures

    def should_stop(self, state: AgentState) -> bool:
        return state.current_step >= state.max_steps or state.status in {"NEEDS_CLARIFICATION", "FAILED"}
