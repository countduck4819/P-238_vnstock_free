"""Bounded, observable execution loop over the existing QueryHarness."""
from __future__ import annotations

from src.services.agent_critic import AgentCritic
from src.services.agent_planner import AgentPlanner
from src.services.agent_state import AgentState, Observation
from src.services.query_harness import QueryHarness


class AgentExecutor:
    def __init__(self, harness: QueryHarness, planner: AgentPlanner | None = None, critic: AgentCritic | None = None) -> None:
        self.harness = harness
        self.planner = planner or AgentPlanner()
        self.critic = critic or AgentCritic()

    def run(self, state: AgentState) -> AgentState:
        state.status = "EXECUTING"
        while state.plan and state.current_step < state.max_steps:
            step = state.plan.pop(0)
            if step.key in {call["key"] for call in state.tool_calls}:
                state.warnings.append("AGENT_REPEATED_TOOL_CALL_SKIPPED")
                continue
            result = self.harness.execute_query(step.query_type, step.params)
            observation = Observation.from_result(result)
            state.tool_calls.append({"key": step.key, "query_type": step.query_type, "params": step.params, "purpose": step.purpose})
            state.observations.append(observation)
            state.completed_steps.append(step.purpose or step.query_type)
            state.current_step += 1
            valid, reason = self.critic.validate_observation(observation)
            if not valid:
                state.status = "FAILED"
                state.warnings.append("AGENT_CRITIC_REJECTED_OBSERVATION")
                state.missing_information.append(reason or "invalid observation")
                return state
            if observation.status in {"MISSING_INPUT", "UNSUPPORTED", "UNSUPPORTED_FOR_MVP", "ZERO_DENOMINATOR", "INVALID_TICKER"}:
                state.warnings.extend(observation.warnings)
                continue
            if not state.plan:
                state.plan = self.planner.replan(state)
        if state.current_step >= state.max_steps and state.plan:
            state.status = "FAILED"
            state.warnings.append("AGENT_MAX_STEPS_REACHED")
        else:
            state.status = "COMPLETED"
        return state
