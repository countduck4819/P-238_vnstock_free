"""Conservative planner for the bounded Financial Research Agent MVP."""
from __future__ import annotations

import json
import re
from typing import Any

from src.services.agent_actions import NextDecision, PlannerAction, PlannerOutput
from src.services.agent_semantics import (
    metric_guidance,
    requires_external_research,
    resolve_analytical_concepts,
)
from src.services.agent_state import AgentState, ToolStep
from src.services.intent_router import (
    create_query_plan,
    normalize_text,
    resolve_metrics,
    resolve_sector,
    resolve_tickers,
    resolve_years,
)
from src.services.llm_client import LLMClient
from src.services.query_tools import ticker_taxonomy

HEALTH_CUES = ("sức khỏe tài chính", "phân tích tài chính", "toàn diện", "năm gần nhất")
COMPLEX_CUES = (
    "phân tích", "sức khỏe", "gần nhất", "nguyên nhân", "đáng chú ý",
    "nhiều năm", "xu hướng",
)
EARNINGS_QUALITY_METRICS = (
    "net_revenue_yoy_growth", "net_profit_yoy_growth", "net_profit_margin",
)


def _is_earnings_quality_comparison(question: Any) -> bool:
    text = normalize_text(question)
    return "so sanh" in text and "chat luong loi nhuan" in text


def _has_cue(text: str, cues: tuple[str, ...]) -> bool:
    return any(normalize_text(cue) in text for cue in cues)


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _sector_for(ticker: str) -> str | None:
    return ticker_taxonomy().get(ticker.upper())


def should_use_agent(question: Any) -> bool:
    text = normalize_text(question)
    if not text:
        return False
    simple_plan = create_query_plan(question)
    tickers, _ = resolve_tickers(str(question))
    metrics = resolve_metrics(str(question))
    complex_signal = (
        _has_cue(text, HEALTH_CUES)
        or any(cue in text for cue in (
            "nguyen nhan", "tai sao", "dang chu y", "nhieu nam", "tang nhung",
            "giam nhung", "dinh gia", "ro re khong", "re khong",
            "rui ro",
        ))
        or bool(re.search(r"(?<!\d)\d+\s+nam\s+gan\s+nhat", text))
        or requires_external_research(str(question))
        or "financial_statement_risk" in resolve_analytical_concepts(str(question))
        or any(
            cue in text
            for cue in (
                "kha nang sinh loi", "suc khoe tai chinh", "hieu qua hay",
                "hieu qua khong", "quy mo lon", "on dinh", "khoe len", "yeu di",
            )
        )
    )
    if simple_plan.get("status") == "OK" and simple_plan.get("intent") != "MULTI_QUERY":
        return bool(len(tickers) > 1 or len(metrics) > 1 or complex_signal)
    return bool(
        len(tickers) > 1
        or len(metrics) > 1
        or complex_signal
        or ("tot khong" in text and metrics)
    )


class AgentPlanner:
    """Creates safe plans from existing router entities; never computes values."""

    def initial_state(self, question: Any, *, max_steps: int = 10) -> AgentState:
        original = str(question or "").strip()
        normalized = normalize_text(original)
        tickers, _ = resolve_tickers(original)
        metrics = resolve_metrics(original)
        concepts = resolve_analytical_concepts(original)
        time = resolve_years(original)
        years = time["years"]
        sector = resolve_sector(original)
        if sector is None and tickers:
            sector = _sector_for(tickers[0])
        goal = concepts[0] if concepts else (
            "financial_health" if _has_cue(normalized, HEALTH_CUES) else "analysis"
        )
        if "tot khong" in normalized:
            goal = "evaluation"
        if len(tickers) > 1:
            goal = "comparison_analysis"
        if "dang chu y" in normalized and "current_events" not in concepts:
            goal = "multi_rank"
        state = AgentState(
            question=original, goal=goal, tickers=tickers, sector=sector,
            period={"years": years, "is_range": time["is_range"]}, max_steps=max_steps,
            status="PLANNING",
        )
        state.plan = self.plan_steps(state, metrics=metrics, years=years, time=time)
        return state

    def plan_steps(
        self, state: AgentState, *, metrics: list[str] | None = None,
        years: list[int] | None = None, time: dict[str, Any] | None = None,
    ) -> list[ToolStep]:
        metrics = metrics or resolve_metrics(state.question)
        concepts = resolve_analytical_concepts(state.question)
        if not metrics:
            metrics = metric_guidance(concepts, state.sector)
        years = years or list((state.period or {}).get("years", []))
        time = time or resolve_years(state.question)
        steps: list[ToolStep] = []
        normalized = normalize_text(state.question)
        dependent_rank = (
            state.sector == "BANK"
            and any(
                cue in normalized
                for cue in ("cao nhat", "nhieu loi nhuan nhat", "kiem nhieu")
            )
        )
        if not state.tickers and dependent_rank:
            if not years:
                state.missing_information.append("year")
                state.status = "NEEDS_CLARIFICATION"
                return steps
            return [ToolStep(
                "RANK",
                {
                    "metric": "net_profit", "year": years[0], "sector": "BANK",
                    "limit": 5, "descending": True,
                },
                "find the highest-profit bank before dependent efficiency analysis",
            )]
        if not state.tickers:
            state.missing_information.append("ticker")
            state.status = "NEEDS_CLARIFICATION"
            return steps

        external_required = requires_external_research(state.question)
        web_step = ToolStep(
            "WEB_SEARCH",
            {"web_query": state.question, "max_results": 5, "recency_days": 365},
            "collect recent verified external context",
        )
        financial_concepts = [value for value in concepts if value != "current_events"]
        if external_required and not financial_concepts and not metrics:
            return [web_step]

        if state.goal == "evaluation":
            return [ToolStep("EVALUATION", {"ticker": state.tickers[0], "year": years[0] if years else None}, "lấy bộ chỉ tiêu mới nhất")]

        if state.goal == "multi_rank":
            if not years:
                return [ToolStep("EVALUATION", {"ticker": state.tickers[0], "year": None}, "xác định năm dữ liệu mới nhất")]
            return [
                ToolStep("RANK", {"metric": metric, "year": years[0], "sector": state.sector, "limit": 5, "descending": True}, f"xếp hạng theo {metric}")
                for metric in _unique(metrics)
            ]

        if time.get("is_range") and len(years) == 2:
            start_year, end_year = sorted(years)
            steps = [
                ToolStep("TIME_SERIES", {"ticker": ticker, "metric": metric, "start_year": start_year, "end_year": end_year}, "phân tích chuỗi thời gian")
                for ticker in state.tickers for metric in _unique(metrics)
            ]
            return [*steps, *([web_step] if external_required else [])]

        if len(years) == 1 and metrics:
            steps = [
                ToolStep(
                    "FACT", {"ticker": ticker, "metric": metric, "year": years[0]},
                    "analyze a supported point-in-time metric",
                )
                for ticker in state.tickers for metric in _unique(metrics)
            ]
            return [*steps, *([web_step] if external_required else [])]

        if state.goal in {
            "financial_health", "comparison_analysis", "analysis", "profitability",
            "growth", "efficiency", "scale", "leverage", "stability",
            "efficiency_vs_scale", "financial_statement_risk",
        }:
            # An EVALUATION observation supplies the latest supported year. The
            # executor then re-plans the requested recent period from evidence.
            if not years or len(years) != 2:
                steps = [
                    ToolStep("EVALUATION", {"ticker": ticker, "year": None}, "xác định năm mới nhất có dữ liệu")
                    for ticker in state.tickers
                ]
                return [*steps, *([web_step] if external_required else [])]
        if external_required:
            return [web_step]
        return []

    def replan(self, state: AgentState) -> list[ToolStep]:
        if state.goal not in {
            "financial_health", "comparison_analysis", "analysis", "profitability",
            "growth", "efficiency", "scale", "leverage", "stability",
            "efficiency_vs_scale", "financial_statement_risk",
        }:
            return []
        eval_obs = [obs for obs in state.observations if obs.tool == "evaluate_stock" and obs.status == "OK"]
        if not eval_obs:
            return []
        text = normalize_text(state.question)
        match = re.search(r"(?<!\d)(\d+)\s+n[aă]m\s+g[aầ]n\s+nh[aấ]t", text)
        count = int(match.group(1)) if match else 3
        metrics = resolve_metrics(state.question)
        if state.goal == "comparison_analysis" and _is_earnings_quality_comparison(state.question):
            metrics = list(EARNINGS_QUALITY_METRICS)
        if not metrics:
            metrics = metric_guidance(
                resolve_analytical_concepts(state.question), state.sector
            )
        if not metrics:
            metrics = ["net_profit"]
        steps: list[ToolStep] = []
        for observation in eval_obs:
            latest = observation.year
            if latest is None:
                continue
            start = latest - count + 1
            for metric in _unique(metrics):
                steps.append(ToolStep(
                    "TIME_SERIES",
                    {"ticker": observation.ticker, "metric": metric, "start_year": start, "end_year": latest},
                    "lấy chuỗi dữ liệu sau khi quan sát năm mới nhất",
                ))
        return steps


PLANNER_SYSTEM_PROMPT = """You are the bounded FinSight financial planner.
Return JSON only. Choose only approved actions: FACT, TIME_SERIES, COMPARE, RANK,
EVALUATION, COMPANY_KNOWLEDGE, WEB_SEARCH. Never invent ticker, year, metric, sector or data.
Never calculate financial values. Ask for missing information instead.
Translate broad analytical concepts into a supported subset of evidence. A clear
profitability, growth, health, efficiency, scale or stability goal does not require
the user to name a raw metric. Use WEB_SEARCH only for current/external context.
The output schema is: {"goal": string, "actions": [PlannerAction],
"missing_information": [string]}."""

DECISION_SYSTEM_PROMPT = """You are the bounded FinSight re-planner.
Inspect only the supplied action summaries and observations. Return JSON only:
{"decision":"CONTINUE|REPLAN|COMPLETE|CLARIFY","reason":string,
"actions":[PlannerAction],"missing_information":[string]}.
Do not invent identifiers, metrics, tools, years or values. Unsupported and missing
results must remain unavailable."""


def _json_object(value: str) -> dict[str, Any]:
    text = str(value or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("Planner output must be a JSON object")
    return parsed


class StructuredAgentPlanner:
    """LLM-assisted planner with a deterministic, schema-safe fallback."""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client
        self.fallback = AgentPlanner()
        self.last_failure: str | None = None

    def initial_plan(
        self, question: str, tickers: list[str], sector: str | None,
        period: dict[str, Any], metrics: list[str],
    ) -> tuple[PlannerOutput, bool]:
        self.last_failure = None
        if self.llm_client is not None:
            prompt = json.dumps({
                "question": question,
                "resolved_entities": {
                    "tickers": tickers, "sector": sector, "period": period,
                    "metrics": metrics,
                },
                "analytical_concepts": resolve_analytical_concepts(question),
                "supported_metric_guidance": metric_guidance(
                    resolve_analytical_concepts(question), sector
                ),
                "external_research_required": requires_external_research(question),
                "constraint": "Use only resolved identifiers or request clarification.",
                "output_schema": PlannerOutput.model_json_schema(),
            }, ensure_ascii=False)
            try:
                raw = self.llm_client.generate(PLANNER_SYSTEM_PROMPT, prompt)
                if not str(raw or "").strip():
                    raise ValueError("EMPTY_PLANNER_RESPONSE")
                output = PlannerOutput.model_validate(_json_object(raw))
                if output.actions and output.missing_information:
                    raise ValueError("CONTRADICTORY_PLANNER_OUTPUT")
                return output, True
            except Exception as exc:  # provider and schema failures use safe fallback
                self.last_failure = f"LLM_PLANNER_FAILURE:{type(exc).__name__}"
        state = self.fallback.initial_state(question)
        output = PlannerOutput(
            goal=state.goal,
            actions=[self._from_step(step) for step in state.plan],
            missing_information=state.missing_information,
        )
        return output, self.llm_client is not None

    def decide_next(
        self, *, question: str, goal: str, remaining: list[PlannerAction],
        observations: list[dict[str, Any]], tickers: list[str], sector: str | None,
    ) -> tuple[NextDecision, bool]:
        self.last_failure = None
        if self.llm_client is not None:
            prompt = json.dumps({
                "question": question, "goal": goal, "resolved_tickers": tickers,
                "resolved_sector": sector,
                "remaining_actions": [action.model_dump() for action in remaining],
                "observations": observations,
                "output_schema": NextDecision.model_json_schema(),
            }, ensure_ascii=False, default=str)
            try:
                raw = self.llm_client.generate(DECISION_SYSTEM_PROMPT, prompt)
                if not str(raw or "").strip():
                    raise ValueError("EMPTY_REPLANNER_RESPONSE")
                output = NextDecision.model_validate(_json_object(raw))
                if output.decision == "REPLAN" and not output.actions:
                    raise ValueError("CONTRADICTORY_REPLANNER_OUTPUT")
                return output, True
            except Exception as exc:  # continue validated work or safely finish
                self.last_failure = f"LLM_REPLANNER_FAILURE:{type(exc).__name__}"
        if remaining:
            return NextDecision(decision="CONTINUE", reason="Execute validated remaining plan"), self.llm_client is not None
        rank_observation = next(
            (
                item for item in reversed(observations)
                if item.get("tool") == "rank" and item.get("status") == "OK"
                and item.get("top_ticker")
            ),
            None,
        )
        if rank_observation:
            top_ticker = str(rank_observation["top_ticker"])
            already_analyzed = any(
                item.get("ticker") == top_ticker
                and item.get("metric") in {"roa", "roe", "total_assets"}
                for item in observations
            )
            if not already_analyzed and rank_observation.get("year"):
                return NextDecision(
                    decision="REPLAN",
                    reason="Use the observed top ticker for efficiency-versus-scale evidence",
                    actions=[
                        PlannerAction(
                            action="FACT", ticker=top_ticker, metric=metric,
                            year=int(rank_observation["year"]),
                            reason="dependent efficiency-versus-scale evidence",
                        )
                        for metric in ("roa", "roe", "total_assets")
                    ],
                ), self.llm_client is not None
        failed = next(
            (
                item for item in reversed(observations)
                if item.get("status") in {
                    "UNSUPPORTED", "UNSUPPORTED_FOR_MVP", "MISSING_INPUT",
                    "ZERO_DENOMINATOR", "NO_RESULTS",
                }
            ),
            None,
        )
        if failed and tickers:
            attempted = {str(item.get("metric")) for item in observations if item.get("metric")}
            alternatives = [
                metric for metric in metric_guidance(
                    resolve_analytical_concepts(question), sector
                )
                if metric not in attempted
            ]
            years = resolve_years(question).get("years") or []
            if alternatives and years:
                if len(years) == 2:
                    action = PlannerAction(
                        action="TIME_SERIES", ticker=tickers[0], metric=alternatives[0],
                        start_year=min(years), end_year=max(years),
                        reason="safe alternate evidence after unsupported or missing result",
                    )
                else:
                    action = PlannerAction(
                        action="FACT", ticker=tickers[0], metric=alternatives[0],
                        year=years[0],
                        reason="safe alternate evidence after unsupported or missing result",
                    )
                return NextDecision(
                    decision="REPLAN", reason="Use a supported alternate evidence path",
                    actions=[action],
                ), self.llm_client is not None
        latest = next(
            (
                item for item in reversed(observations)
                if item.get("tool") == "evaluate_stock" and item.get("status") == "OK"
            ),
            None,
        )
        has_trend = any(item.get("tool") == "get_timeseries" for item in observations)
        if latest and not has_trend and goal in {
            "financial_health", "comparison_analysis", "analysis", "profitability",
            "growth", "efficiency", "scale", "leverage", "stability",
            "efficiency_vs_scale", "financial_statement_risk",
        }:
            text = normalize_text(question)
            match = re.search(r"(?<!\d)(\d+)\s+nam\s+gan\s+nhat", text)
            count = int(match.group(1)) if match else 3
            latest_year = latest.get("year")
            ticker = latest.get("ticker")
            metrics = resolve_metrics(question)
            if goal == "comparison_analysis" and _is_earnings_quality_comparison(question):
                metrics = list(EARNINGS_QUALITY_METRICS)
            if not metrics:
                metrics = metric_guidance(resolve_analytical_concepts(question), sector)
            if latest_year and ticker:
                trend_tickers = tickers if goal == "comparison_analysis" else [ticker]
                return NextDecision(
                    decision="REPLAN",
                    reason="Latest supported year observed; expand into deterministic trends",
                    actions=[
                        PlannerAction(
                            action="TIME_SERIES", ticker=trend_ticker, metric=metric,
                            start_year=int(latest_year) - count + 1,
                            end_year=int(latest_year), reason="Assess supported trend",
                        )
                        for trend_ticker in trend_tickers
                        for metric in (metrics or ["net_profit"])
                    ],
                ), self.llm_client is not None
        return NextDecision(
            decision="COMPLETE", reason="No additional validated action required"
        ), self.llm_client is not None

    @staticmethod
    def _from_step(step: ToolStep) -> PlannerAction:
        params = dict(step.params)
        if step.query_type == "TIME_SERIES":
            return PlannerAction(action="TIME_SERIES", reason=step.purpose, **params)
        return PlannerAction(action=step.query_type, reason=step.purpose, **params)
