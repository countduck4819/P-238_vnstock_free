"""LangGraph orchestration for the bounded Financial Research Agent."""
from __future__ import annotations

from html import escape
from typing import Any

from langgraph.graph import END, START, StateGraph

from src.services.agent_actions import ActionValidator, PlannerAction, registered_tool
from src.services.agent_budget import AgentBudget
from src.services.agent_critic import AgentCritic
from src.services.agent_planner import StructuredAgentPlanner
from src.services.agent_semantics import (
    requires_external_research,
    resolve_analytical_concepts,
)
from src.services.agent_state import LangGraphAgentState, Observation
from src.services.agent_synthesis import (
    GroundedSynthesizer,
    SynthesisClaimValidator,
    compact_observation,
    deterministic_analytical_summary,
    normalize_evidence,
)
from src.services.agent_trace import append_trace
from src.services.analyst_report import AnalystReportGenerator
from src.services.benchmark_engine import BenchmarkAnalyzer
from src.services.data_availability import DataAvailabilityResolver
from src.services.evidence_fusion import EvidenceFusionNode
from src.services.evidence_planning import EvidencePlanningSkill
from src.services.external_data_recovery import ExternalFinancialDataRecoveryAgent
from src.services.financial_interpretation import FinancialInterpretationEngine
from src.services.financial_question_understanding import FinancialQuestionUnderstandingSkill
from src.services.financial_reasoning import FinancialAnalysisResult, FinancialReasoningEngine
from src.services.intent_router import (
    normalize_text,
    resolve_metrics,
    resolve_sector,
    resolve_tickers,
    resolve_years,
)
from src.services.query_harness import QueryHarness
from src.services.response_composer import compose_response
from src.services.risk_review import RiskReviewEngine
from src.services.web_research import ControlledWebResearch


def _trace(state: LangGraphAgentState, node: str, decision: str, **extra: Any) -> list[dict[str, Any]]:
    return append_trace(state.get("trace") or [], node, decision, **extra)


class FinancialAgentGraph:
    def __init__(
        self, harness: QueryHarness, planner: StructuredAgentPlanner,
        *, budget: AgentBudget | None = None,
        web_research: ControlledWebResearch | None = None,
    ) -> None:
        self.harness = harness
        self.planner = planner
        # Keep the existing planner/synthesis LLM budget and call order stable.
        # The skill accepts an LLM for opt-in refinement when used standalone;
        # the graph uses its deterministic, rule-grounded mode by default.
        self.question_understanding = FinancialQuestionUnderstandingSkill(None)
        self.evidence_planning = EvidencePlanningSkill()
        self.data_availability = DataAvailabilityResolver()
        self.evidence_fusion = EvidenceFusionNode()
        self.financial_reasoning = FinancialReasoningEngine(self.evidence_fusion)
        self.financial_interpretation = FinancialInterpretationEngine()
        self.benchmark_analyzer = BenchmarkAnalyzer()
        self.risk_review_engine = RiskReviewEngine()
        self.report_generator = AnalystReportGenerator()
        self.safe_planner = StructuredAgentPlanner(None)
        self.validator = ActionValidator()
        self.critic = AgentCritic()
        self.synthesizer = GroundedSynthesizer(planner.llm_client)
        self.synthesis_validator = SynthesisClaimValidator()
        self.web_research = web_research
        self.budget = (budget or AgentBudget.from_env()).bounded()
        if self.web_research is not None:
            self.web_research.policy.max_sources = min(
                self.web_research.policy.max_sources, self.budget.max_web_sources
            )
            self.web_research.policy.max_total_content = min(
                self.web_research.policy.max_total_content,
                self.budget.max_external_content,
            )
        self.graph = self._build()

    def _build(self):
        graph = StateGraph(LangGraphAgentState)
        graph.add_node("route_request", self.route_request)
        graph.add_node("interpret_goal", self.interpret_goal)
        graph.add_node("understand_question", self.understand_question)
        graph.add_node("plan_evidence", self.plan_evidence)
        graph.add_node("analyze_availability", self.analyze_availability)
        graph.add_node("recover_external_data", self.recover_external_data)
        graph.add_node("fuse_evidence", self.fuse_evidence)
        graph.add_node("financial_reasoning", self.reason_financials)
        graph.add_node("financial_interpretation", self.interpret_financials)
        graph.add_node("benchmark_analysis", self.analyze_benchmarks)
        graph.add_node("risk_review", self.review_risks)
        graph.add_node("analyst_report_generator", self.generate_report)
        graph.add_node("plan", self.plan)
        graph.add_node("validate_action", self.validate_action)
        graph.add_node("execute_tool", self.execute_tool)
        graph.add_node("observe", self.observe)
        graph.add_node("decide_next", self.decide_next)
        graph.add_node("critic", self.run_critic)
        graph.add_node("synthesize", self.synthesize)
        graph.add_node("validate_synthesis", self.validate_synthesis)
        graph.add_node("compose", self.compose)
        graph.add_edge(START, "route_request")
        graph.add_conditional_edges(
            "route_request", lambda state: state.get("decision", "COMPLEX"),
            {"COMPLEX": "interpret_goal", "FAIL": "compose"},
        )
        graph.add_conditional_edges(
            "interpret_goal", lambda state: state.get("decision", "PLAN"),
            {"PLAN": "plan", "CLARIFY": "compose"},
        )
        graph.add_conditional_edges(
            "plan", lambda state: state.get("decision", "VALIDATE"),
            {"VALIDATE": "understand_question", "CLARIFY": "compose", "FAIL": "compose"},
        )
        graph.add_edge("understand_question", "plan_evidence")
        graph.add_edge("plan_evidence", "analyze_availability")
        graph.add_edge("analyze_availability", "recover_external_data")
        graph.add_edge("recover_external_data", "fuse_evidence")
        graph.add_edge("fuse_evidence", "validate_action")
        graph.add_conditional_edges(
            "validate_action", lambda state: state.get("decision", "EXECUTE"),
            {
                "EXECUTE": "execute_tool", "REPLAN": "decide_next",
                "COMPLETE": "critic", "FAIL": "critic",
            },
        )
        graph.add_edge("execute_tool", "observe")
        graph.add_edge("observe", "decide_next")
        graph.add_conditional_edges(
            "decide_next", lambda state: state.get("decision", "COMPLETE"),
            {
                "CONTINUE": "validate_action", "REPLAN": "plan",
                "COMPLETE": "critic", "CLARIFY": "compose", "FAIL": "critic",
            },
        )
        graph.add_edge("critic", "financial_reasoning")
        graph.add_edge("financial_reasoning", "financial_interpretation")
        graph.add_edge("financial_interpretation", "benchmark_analysis")
        graph.add_edge("benchmark_analysis", "risk_review")
        graph.add_edge("risk_review", "analyst_report_generator")
        graph.add_edge("analyst_report_generator", "synthesize")
        graph.add_edge("synthesize", "validate_synthesis")
        graph.add_edge("validate_synthesis", "compose")
        graph.add_edge("compose", END)
        return graph.compile()

    def invoke(self, question: str) -> LangGraphAgentState:
        initial: LangGraphAgentState = {
            "question": str(question), "goal": "", "analytical_concepts": [],
            "financial_blueprint": None, "blueprint_used": False,
            "evidence_plan": None,
            "data_availability": None,
            "external_recovery_evidence": [],
            "evidence_package": None,
            "financial_analysis_result": None,
            "financial_signals": None,
            "benchmark_result": None,
            "risk_review": None,
            "analyst_report": None,
            "tickers": [], "sector": None,
            "period": {}, "plan": [], "pending_action": None,
            "observations": [], "tool_calls": [], "evidence": [],
            "normalized_evidence": [], "compact_observations": [], "warnings": [],
            "missing_information": [], "iteration_count": 0,
            "max_iterations": self.budget.max_iterations, "status": "PLANNING",
            "decision": "COMPLEX", "final_answer": "", "results": [], "trace": [],
            "invalid_action_count": 0, "llm_call_count": 0,
            "tool_call_count": 0, "replan_count": 0,
            "max_llm_calls": self.budget.max_llm_calls,
            "max_tool_calls": self.budget.max_tool_calls,
            "max_replans": self.budget.max_replans,
            "synthesis_draft": None, "synthesis_valid": False,
            "external_research_required": False, "web_queries": [],
            "web_sources": [], "external_evidence": [], "source_conflicts": [],
            "claim_types": [], "research_complete": False,
            "web_call_count": 0, "max_web_calls": self.budget.max_web_calls,
        }
        return self.graph.invoke(initial)

    def understand_question(self, state: LangGraphAgentState) -> dict[str, Any]:
        """Create the answer-free blueprint before tool planning."""
        if (
            self.question_understanding.llm_client is not None
            and state.get("llm_call_count", 0) >= state.get("max_llm_calls", 5)
        ):
            self.question_understanding.llm_client = None
        blueprint = self.question_understanding.understand(state["question"])
        warnings = list(state.get("warnings") or [])
        if self.question_understanding.last_failure:
            warnings.append(self.question_understanding.last_failure)
        calls = state.get("llm_call_count", 0) + int(self.question_understanding.last_used_llm)
        return {
            "financial_blueprint": blueprint.model_dump(mode="json"),
            "blueprint_used": True,
            "llm_call_count": calls,
            "warnings": warnings,
            "trace": _trace(
                state, "understand_question",
                "LLM_REFINED" if self.question_understanding.last_used_llm else "DETERMINISTIC_FALLBACK",
                intent=blueprint.intent.value,
                evidence_count=len(blueprint.required_evidence),
            ),
        }

    def route_request(self, state: LangGraphAgentState) -> dict[str, Any]:
        return {
            "decision": "COMPLEX",
            "trace": _trace(state, "route_request", "LANGGRAPH_USED", status="COMPLEX"),
        }

    def plan_evidence(self, state: LangGraphAgentState) -> dict[str, Any]:
        """Plan evidence sources without reading any source."""
        blueprint = state.get("financial_blueprint")
        if not blueprint:
            return {
                "evidence_plan": None,
                "warnings": [*(state.get("warnings") or []), "EVIDENCE_PLAN_MISSING_BLUEPRINT"],
                "trace": _trace(state, "plan_evidence", "SKIP", status="MISSING_BLUEPRINT"),
            }
        plan = self.evidence_planning.plan(blueprint)
        actions = list(state.get("plan") or [])
        # Evidence planning supplies a deterministic recovery plan only when
        # the planner produced no executable actions. Existing planner output
        # remains authoritative to preserve ordering and duplicate guards.
        if not actions:
            actions.extend(self._missing_evidence_actions(state, plan, actions))
        return {
            "evidence_plan": plan.model_dump(mode="json"),
            "plan": actions,
            "trace": _trace(
                state, "plan_evidence", "PLANNED",
                evidence_count=len(plan.evidence_items),
            ),
        }

    @staticmethod
    def _missing_evidence_actions(
        state: LangGraphAgentState, plan: Any, existing: list[PlannerAction]
    ) -> list[PlannerAction]:
        """Map uncovered EvidencePlan items to registered actions deterministically."""
        tickers = state.get("tickers") or []
        if not tickers:
            return []
        years = [int(value) for value in (state.get("period") or {}).get("years", []) if isinstance(value, int)]
        start_year, end_year = (min(years), max(years)) if len(years) >= 2 else (None, None)
        metric_map = {
            "revenue": "net_revenue", "revenue_growth": "net_revenue_yoy_growth",
            "profit": "net_profit", "profit_growth": "net_profit_yoy_growth",
            "net_margin": "net_profit_margin", "total_assets": "total_assets",
            "total_liabilities": "total_liabilities", "total_equity": "total_equity",
            "roa": "roa", "roe": "roe", "cash_flow": "cash_flow",
            "valuation_multiple": "valuation_multiple",
        }
        covered = {
            (action.action, action.ticker, action.metric, action.start_year, action.end_year, action.year)
            for action in existing
        }
        additions: list[PlannerAction] = []
        for item in plan.evidence_items:
            name = str(item.name)
            if name in metric_map:
                metric = metric_map[name]
                if start_year is not None and end_year is not None and start_year != end_year:
                    candidate = PlannerAction(
                        action="TIME_SERIES", ticker=tickers[0], metric=metric,
                        start_year=start_year, end_year=end_year,
                        reason="evidence plan coverage",
                    )
                elif end_year is not None:
                    candidate = PlannerAction(
                        action="FACT", ticker=tickers[0], metric=metric, year=end_year,
                        reason="evidence plan coverage",
                    )
                else:
                    candidate = PlannerAction(
                        action="EVALUATION", ticker=tickers[0], year=None,
                        reason="evidence plan coverage",
                    )
            elif name in {"business_driver", "company_profile", "management", "industry_context"}:
                candidate = PlannerAction(
                    action="COMPANY_KNOWLEDGE", ticker=tickers[0], query_text=plan.objective,
                    document_types=["management" if name == "management" else "company_profile"],
                    reason="evidence plan qualitative coverage",
                )
            else:
                continue
            signature = (candidate.action, candidate.ticker, candidate.metric,
                         candidate.start_year, candidate.end_year, candidate.year)
            if signature not in covered:
                additions.append(candidate)
                covered.add(signature)
        return additions

    def analyze_availability(self, state: LangGraphAgentState) -> dict[str, Any]:
        """Check declared source/metric capabilities without performing I/O."""
        plan = state.get("evidence_plan")
        if not plan:
            return {
                "data_availability": None,
                "warnings": [*(state.get("warnings") or []), "DATA_AVAILABILITY_MISSING_EVIDENCE_PLAN"],
                "trace": _trace(state, "analyze_availability", "SKIP", status="MISSING_PLAN"),
            }
        report = self.data_availability.resolve(plan)
        return {
            "data_availability": report.model_dump(mode="json"),
            "trace": _trace(
                state, "analyze_availability", "ANALYZED",
                available=len(report.available), derivable=len(report.derivable),
                missing=len(report.missing), external_required=len(report.external_required),
            ),
        }

    def recover_external_data(self, state: LangGraphAgentState) -> dict[str, Any]:
        """Recover only explicitly missing evidence; never write it to PostgreSQL."""
        report = state.get("data_availability") or {}
        missing = list(report.get("missing") or [])
        if self.web_research is None or not missing or not state.get("tickers"):
            return {
                "external_recovery_evidence": [],
                "trace": _trace(state, "recover_external_data", "SKIP", status="NO_RECOVERY_REQUIRED"),
            }
        year_value = (state.get("period") or {}).get("end_year")
        if year_value is None:
            years = (state.get("period") or {}).get("years") or []
            year_value = years[-1] if years else None
        year = year_value if isinstance(year_value, int) else None
        request = {
            "company": state["tickers"][0],
            "missing": [{"metric": item.get("evidence", ""), "year": year} for item in missing],
        }
        result = ExternalFinancialDataRecoveryAgent(self.web_research.client).recover(request)
        evidence = result.model_dump(mode="json")["evidence"]
        return {
            "external_recovery_evidence": evidence,
            "trace": _trace(
                state, "recover_external_data", "RECOVERED" if evidence else "NO_RESULTS",
                evidence_count=len(evidence),
            ),
        }

    def fuse_evidence(self, state: LangGraphAgentState) -> dict[str, Any]:
        """Create one provenance-preserving package; no numerical rewriting."""
        postgres: list[dict[str, Any]] = []
        derived: list[dict[str, Any]] = []
        qdrant: list[dict[str, Any]] = []
        external = list(state.get("external_recovery_evidence") or [])
        for observation in state.get("observations") or []:
            source = str(observation.source or "").upper()
            rows = observation.data or []
            if "QDRANT" in source or observation.tool == "search_company_knowledge":
                qdrant.extend(rows)
            elif "DERIVED" in source:
                derived.extend(rows)
            elif "WEB" in source or observation.tool == "web_search":
                external.extend(rows)
            else:
                postgres.extend(rows)
        package = self.evidence_fusion.fuse(postgres, derived, qdrant, external)
        return {
            "evidence_package": package.model_dump(mode="json"),
            "trace": _trace(
                state, "fuse_evidence", "FUSED",
                facts=len(package.facts), interpretations=len(package.interpretations),
                conflict=package.conflict,
            ),
        }

    def reason_financials(self, state: LangGraphAgentState) -> dict[str, Any]:
        """Run evidence-bounded reasoning after the critic has observed tools."""
        package_data = state.get("evidence_package")
        if state.get("observations"):
            package_data = self.fuse_evidence(state).get("evidence_package")
        if not package_data:
            package_data = {
                "facts": [], "interpretations": [], "confidence": "LOW", "limitations": [],
            }
        result: FinancialAnalysisResult = self.financial_reasoning.analyze(package_data)
        return {
            "evidence_package": package_data,
            "financial_analysis_result": result.model_dump(mode="json"),
            "trace": _trace(
                state, "financial_reasoning", "ANALYZED",
                confidence_score=result.confidence_score,
            ),
        }

    def interpret_financials(self, state: LangGraphAgentState) -> dict[str, Any]:
        """Convert grounded reasoning into non-advisory financial signals."""
        analysis = state.get("financial_analysis_result")
        if not analysis:
            return {
                "financial_signals": None,
                "trace": _trace(state, "financial_interpretation", "SKIP", status="MISSING_ANALYSIS"),
            }
        signals = self.financial_interpretation.interpret(analysis)
        return {
            "financial_signals": signals.model_dump(mode="json"),
            "trace": _trace(
                state, "financial_interpretation", "INTERPRETED",
                signal_count=len(signals.signals), confidence=signals.confidence,
            ),
        }

    def analyze_benchmarks(self, state: LangGraphAgentState) -> dict[str, Any]:
        """Compare only source-backed package facts to registered benchmarks."""
        package = state.get("evidence_package") or {}
        facts = package.get("facts") or []
        ticker = (state.get("tickers") or ["UNKNOWN"])[0]
        metrics = [{
            "metric": item.get("metric", ""), "value": item.get("value"),
            "source": item.get("source", ""),
            "evidence_refs": [f"fact:{item.get('metric')}:{item.get('year') or 'undated'}"],
            "year": item.get("year"),
        } for item in facts if item.get("value") is not None and item.get("source")]
        result = self.benchmark_analyzer.analyze({
            "company": ticker, "metrics": metrics,
            "signals": state.get("financial_signals", {}).get("signals", []),
        })
        return {
            "benchmark_result": result.model_dump(mode="json"),
            "trace": _trace(
                state, "benchmark_analysis", "ANALYZED",
                benchmark_count=len(result.benchmarks),
            ),
        }

    def review_risks(self, state: LangGraphAgentState) -> dict[str, Any]:
        """Review risk signals without retrieving or modifying evidence."""
        analysis = state.get("financial_analysis_result")
        signals = state.get("financial_signals")
        benchmark = state.get("benchmark_result")
        if not analysis or not signals or not benchmark:
            return {
                "risk_review": None,
                "trace": _trace(state, "risk_review", "SKIP", status="MISSING_INPUT"),
            }
        result = self.risk_review_engine.review({
            "financial_analysis_result": analysis,
            "financial_signals": signals,
            "benchmark_result": benchmark,
        })
        return {
            "risk_review": result.model_dump(mode="json"),
            "trace": _trace(
                state, "risk_review", "REVIEWED",
                risk_count=len(result.risks), level=result.overall_risk_level.value,
            ),
        }

    def generate_report(self, state: LangGraphAgentState) -> dict[str, Any]:
        """Render a traceable report from structured analysis only."""
        analysis = state.get("financial_analysis_result")
        signals = state.get("financial_signals")
        benchmark = state.get("benchmark_result")
        risk_review = state.get("risk_review")
        if not analysis or not signals or not benchmark or not risk_review:
            return {
                "analyst_report": None,
                "trace": _trace(state, "analyst_report_generator", "SKIP", status="MISSING_INPUT"),
            }
        report = self.report_generator.generate({
            "financial_analysis_result": analysis,
            "financial_signals": signals,
            "benchmark_result": benchmark,
            "risk_review": risk_review,
        })
        return {
            "analyst_report": report.model_dump(mode="json"),
            "trace": _trace(
                state, "analyst_report_generator", "GENERATED",
                evidence_coverage=report.evidence_coverage,
            ),
        }

    def interpret_goal(self, state: LangGraphAgentState) -> dict[str, Any]:
        question = state["question"]
        concepts = resolve_analytical_concepts(question)
        tickers, _ = resolve_tickers(question)
        period = resolve_years(question)
        sector = resolve_sector(question)
        if sector is None and tickers:
            from src.services.query_tools import ticker_taxonomy
            sector = ticker_taxonomy().get(tickers[0])
        # Analytical complex requests need a concrete ticker unless they are
        # explicit sector rankings handled by the deterministic fast path.
        if not tickers and sector is None:
            return {
                "tickers": [], "sector": sector, "period": period,
                "analytical_concepts": concepts,
                "external_research_required": requires_external_research(question),
                "missing_information": ["ticker"], "status": "NEEDS_CLARIFICATION",
                "decision": "CLARIFY",
                "trace": _trace(state, "interpret_goal", "CLARIFY", status="MISSING_TICKER"),
            }
        return {
            "tickers": tickers, "sector": sector, "period": period,
            "analytical_concepts": concepts,
            "external_research_required": requires_external_research(question),
            "decision": "PLAN",
            "trace": _trace(state, "interpret_goal", "PLAN", status="ENTITIES_RESOLVED"),
        }

    def plan(self, state: LangGraphAgentState) -> dict[str, Any]:
        warnings = list(state.get("warnings") or [])
        planner = self.planner
        if (
            planner.llm_client is not None
            and state.get("llm_call_count", 0) >= state.get("max_llm_calls", 5)
        ):
            planner = self.safe_planner
            warnings.append("AGENT_MAX_LLM_CALLS_REACHED")
        output, used_llm = planner.initial_plan(
            state["question"], state["tickers"], state.get("sector"),
            state.get("period") or {}, resolve_metrics(state["question"]),
        )
        if planner.last_failure:
            warnings.append(planner.last_failure)
        calls = state.get("llm_call_count", 0) + int(used_llm)
        if output.missing_information or not output.actions:
            return {
                "goal": output.goal,
                "missing_information": output.missing_information or ["supported analytical action"],
                "status": "NEEDS_CLARIFICATION", "decision": "CLARIFY",
                "trace": _trace(state, "plan", "CLARIFY", status="NO_ACTION"),
                "llm_call_count": calls,
                "warnings": warnings,
            }
        return {
            "goal": output.goal, "plan": output.actions, "decision": "VALIDATE",
            "trace": _trace(
                state, "plan", "LLM_PLAN_USED" if used_llm else "DETERMINISTIC_FALLBACK",
                status=f"{len(output.actions)}_ACTIONS",
            ),
            "llm_call_count": calls,
            "warnings": warnings,
        }

    def validate_action(self, state: LangGraphAgentState) -> dict[str, Any]:
        plan = list(state.get("plan") or [])
        if not plan:
            return {"decision": "COMPLETE", "trace": _trace(state, "validate_action", "COMPLETE")}
        if state.get("tool_call_count", 0) >= state.get("max_tool_calls", 10):
            useful = bool(state.get("evidence"))
            return {
                "decision": "FAIL", "status": "PARTIAL" if useful else "FAILED",
                "warnings": [*(state.get("warnings") or []), "AGENT_MAX_TOOL_CALLS_REACHED"],
                "trace": _trace(state, "validate_action", "FAIL", status="MAX_TOOL_CALLS"),
            }
        action = plan.pop(0)
        if action.action == "WEB_SEARCH" and not state.get("external_research_required"):
            return {
                "plan": plan, "pending_action": None, "decision": "FAIL",
                "status": "PARTIAL" if state.get("evidence") else "FAILED",
                "warnings": [
                    *(state.get("warnings") or []),
                    "WEB_SEARCH_NOT_REQUIRED",
                    "LLM_PLANNER_FAILURE: disallowed external research action",
                ],
                "trace": _trace(
                    state, "validate_action", "REJECT", tool="WEB_SEARCH",
                    status="WEB_SEARCH_NOT_REQUIRED",
                ),
            }
        if (
            action.action == "WEB_SEARCH"
            and state.get("web_call_count", 0) >= state.get("max_web_calls", 4)
        ):
            return {
                "plan": plan, "pending_action": None, "decision": "FAIL",
                "status": "PARTIAL" if state.get("evidence") else "FAILED",
                "warnings": [*(state.get("warnings") or []), "AGENT_MAX_WEB_CALLS_REACHED"],
                "trace": _trace(
                    state, "validate_action", "FAIL", tool="WEB_SEARCH",
                    status="MAX_WEB_CALLS",
                ),
            }
        executed = {call["key"] for call in state.get("tool_calls") or []}
        requested_years = {
            int(value) for value in (state.get("period") or {}).get("years", [])
            if isinstance(value, int)
        }
        observed_years = {
            int(value)
            for observation in state.get("observations") or []
            for value in (
                observation.year,
                (observation.period or {}).get("end_year") if observation.period else None,
            )
            if isinstance(value, int)
        }
        grounded_tickers = set(state.get("tickers") or [])
        for summary in state.get("compact_observations") or []:
            grounded_tickers.update(summary.get("tickers") or [])
            if summary.get("top_ticker"):
                grounded_tickers.add(summary["top_ticker"])
        valid, reason = self.validator.validate(
            action, executed,
            allowed_tickers=grounded_tickers,
            requested_years=requested_years,
            observed_years=observed_years,
        )
        if not valid:
            warnings = [*(state.get("warnings") or []), reason or "INVALID_ACTION"]
            useful = bool(state.get("evidence"))
            return {
                "plan": plan, "pending_action": None,
                "invalid_action_count": state.get("invalid_action_count", 0) + 1,
                "warnings": warnings,
                "status": "PARTIAL" if useful else "FAILED",
                "decision": "REPLAN" if useful else "FAIL",
                "trace": _trace(
                    state, "validate_action", "REJECT", tool=action.action,
                    params=action.to_params(), status=reason,
                ),
            }
        return {
            "plan": plan, "pending_action": action, "decision": "EXECUTE",
            "trace": _trace(
                state, "validate_action", "ACCEPT", tool=action.action,
                params=action.to_params(), status="VALID",
            ),
        }

    def execute_tool(self, state: LangGraphAgentState) -> dict[str, Any]:
        action = state.get("pending_action")
        if action is None:
            return {"decision": "FAIL", "status": "FAILED"}
        params = action.to_params()
        if action.action == "WEB_SEARCH":
            if self.web_research is None:
                result = {
                    "tool": "web_search", "status": "TOOL_UNAVAILABLE",
                    "query": params.get("query"), "data": [], "web_sources": [],
                    "rejected_sources": [], "source_conflicts": [], "source": "WEB",
                    "warnings": [],
                    "errors": [{"code": "WEB_SEARCH_NOT_CONFIGURED"}],
                }
            else:
                result = self.web_research.search(**params)
            if len(state.get("tickers") or []) == 1:
                result["ticker"] = state["tickers"][0]
        else:
            try:
                if registered_tool(action.action) is None:
                    raise RuntimeError("TOOL_NOT_REGISTERED")
                result = self.harness.execute_query(action.action, params)
            except Exception as exc:
                if action.action == "COMPANY_KNOWLEDGE" and self.web_research is not None:
                    # Qualitative retrieval can fall back to controlled
                    # external research without relabeling it as Qdrant data.
                    result = self.web_research.search(
                        query=str(params.get("query_text") or state.get("question") or ""),
                        max_results=5,
                    )
                    result.setdefault("warnings", []).append("QDRANT_FALLBACK_EXTERNAL_RESEARCH")
                    if len(state.get("tickers") or []) == 1:
                        result["ticker"] = state["tickers"][0]
                    # Continue through the normal observation/fusion path.
                    calls = [*(state.get("tool_calls") or []), {
                        "key": action.key, "query_type": action.action,
                        "params": action.to_params(), "purpose": action.reason,
                    }]
                    iteration = state.get("iteration_count", 0) + 1
                    return {
                        "tool_calls": calls, "results": [*(state.get("results") or []), result],
                        "iteration_count": iteration,
                        "tool_call_count": state.get("tool_call_count", 0) + 1,
                        "web_call_count": state.get("web_call_count", 0) + 1,
                        "trace": _trace(
                            state, "execute_tool", "QDRANT_FALLBACK_EXTERNAL",
                            tool=action.action, params=params, status=result.get("status"),
                        ),
                    }
                # Provider/database exception messages can contain connection details.
                # Preserve only the exception class in public state and trace.
                result = {
                    "tool": action.action.lower(),
                    "status": "TOOL_UNAVAILABLE",
                    "ticker": action.ticker,
                    "tickers": action.tickers,
                    "metric": action.metric,
                    "year": action.year or action.end_year,
                    "period": (
                        {"start_year": action.start_year, "end_year": action.end_year}
                        if action.action == "TIME_SERIES"
                        else None
                    ),
                    "data": [],
                    "source": "QDRANT" if action.action == "COMPANY_KNOWLEDGE" else "POSTGRESQL",
                    "warnings": [],
                    "errors": [{
                        "code": "TOOL_EXECUTION_FAILED",
                        "message": type(exc).__name__,
                    }],
                }
        calls = [*(state.get("tool_calls") or []), {
            "key": action.key, "query_type": action.action,
            "params": action.to_params(), "purpose": action.reason,
        }]
        iteration = state.get("iteration_count", 0) + 1
        return {
            "tool_calls": calls, "results": [*(state.get("results") or []), result],
            "iteration_count": iteration,
            "tool_call_count": state.get("tool_call_count", 0) + 1,
            "web_call_count": state.get("web_call_count", 0) + int(action.action == "WEB_SEARCH"),
            "web_queries": [
                *(state.get("web_queries") or []),
                *([str(params.get("query") or "")] if action.action == "WEB_SEARCH" else []),
            ],
            "trace": _trace(
                state, "execute_tool",
                "WEB_SEARCH_USED" if action.action == "WEB_SEARCH" else "TOOL_EXECUTED",
                tool=action.action,
                params=params, status=result.get("status"),
            ),
        }

    def observe(self, state: LangGraphAgentState) -> dict[str, Any]:
        observation = Observation.from_result(state["results"][-1])
        observations = [*(state.get("observations") or []), observation]
        evidence = list(state.get("evidence") or [])
        if observation.status == "OK":
            evidence.extend(observation.data)
        normalized = normalize_evidence(observations)
        compact = compact_observation(observation, len(observations) - 1)
        compact_observations = [*(state.get("compact_observations") or []), compact]
        latest_result = state["results"][-1]
        accepted_sources = list(latest_result.get("web_sources") or [])
        rejected_sources = list(latest_result.get("rejected_sources") or [])
        conflicts = list(latest_result.get("source_conflicts") or [])
        trace = _trace(
            state, "observe", "OBSERVATION_RECEIVED", tool=observation.tool,
            status=observation.status, observation_summary=compact,
        )
        for source in accepted_sources:
            trace = append_trace(
                trace, "observe", "WEB_SOURCE_ACCEPTED",
                status=source.get("reliability"),
                source_id=source.get("source_id"), domain=source.get("domain"),
            )
        for source in rejected_sources[:10]:
            trace = append_trace(
                trace, "observe", "WEB_SOURCE_REJECTED",
                status=source.get("reason"), url=source.get("url"),
            )
        if conflicts:
            trace = append_trace(
                trace, "observe", "SOURCE_CONFLICT", status=f"{len(conflicts)}_CONFLICTS"
            )
        return {
            "observations": observations, "evidence": evidence,
            "normalized_evidence": normalized,
            "compact_observations": compact_observations,
            "web_sources": [*(state.get("web_sources") or []), *accepted_sources],
            "external_evidence": [
                *(state.get("external_evidence") or []), *accepted_sources,
            ],
            "source_conflicts": [*(state.get("source_conflicts") or []), *conflicts],
            "research_complete": bool(accepted_sources) or not state.get("external_research_required"),
            "warnings": [
                *(state.get("warnings") or []),
                *(["WEB_SOURCE_CONFLICT"] if conflicts else []),
            ],
            "pending_action": None,
            "trace": trace,
        }

    def decide_next(self, state: LangGraphAgentState) -> dict[str, Any]:
        if state.get("iteration_count", 0) >= state.get("max_iterations", 10):
            useful = bool(state.get("evidence"))
            return {
                "decision": "FAIL", "status": "PARTIAL" if useful else "FAILED",
                "warnings": [*(state.get("warnings") or []), "AGENT_MAX_ITERATIONS_REACHED"],
                "trace": _trace(state, "decide_next", "FAIL", status="MAX_ITERATIONS"),
            }
        summaries = list(state.get("compact_observations") or [])
        warnings = list(state.get("warnings") or [])
        planner = self.planner
        latest_status = summaries[-1].get("status") if summaries else None
        if state.get("plan") and latest_status == "OK":
            planner = self.safe_planner
        budget_reached = (
            self.planner.llm_client is not None
            and state.get("llm_call_count", 0) >= state.get("max_llm_calls", 5)
        )
        if budget_reached:
            planner = self.safe_planner
            warnings.append("AGENT_MAX_LLM_CALLS_REACHED")
        decision, used_llm = planner.decide_next(
            question=state["question"], goal=state.get("goal", ""),
            remaining=list(state.get("plan") or []), observations=summaries,
            tickers=state.get("tickers") or [], sector=state.get("sector"),
        )
        if planner.last_failure:
            warnings.append(planner.last_failure)
        updates: dict[str, Any] = {
            "decision": decision.decision,
            "trace": _trace(
                state, "decide_next", decision.decision, status="STRUCTURED_DECISION"
            ),
            "llm_call_count": state.get("llm_call_count", 0) + int(used_llm),
            "warnings": warnings,
        }
        if used_llm and decision.decision == "REPLAN":
            updates["trace"] = _trace(
                state, "decide_next", "LLM_REPLAN_USED", status="STRUCTURED_DECISION"
            )
        if decision.decision == "REPLAN":
            if not decision.actions:
                updates["decision"] = "COMPLETE" if state.get("evidence") else "FAIL"
            elif state.get("replan_count", 0) >= state.get("max_replans", 3):
                useful = bool(state.get("evidence"))
                updates.update({
                    "decision": "COMPLETE" if useful else "FAIL",
                    "status": "PARTIAL" if useful else "FAILED",
                    "warnings": [*warnings, "AGENT_MAX_REPLANS_REACHED"],
                })
            else:
                # Re-planning actions are already structured, but still must pass validate_action.
                updates["plan"] = decision.actions
                updates["decision"] = "CONTINUE"
                updates["replan_count"] = state.get("replan_count", 0) + 1
        elif decision.decision == "CONTINUE" and not state.get("plan"):
            updates["decision"] = "COMPLETE"
        elif decision.decision == "CLARIFY":
            updates["status"] = "NEEDS_CLARIFICATION"
            updates["missing_information"] = decision.missing_information
        if budget_reached and state.get("evidence"):
            updates["status"] = "PARTIAL"
        return updates

    def run_critic(self, state: LangGraphAgentState) -> dict[str, Any]:
        valid, failures = self.critic.validate_observations(state.get("observations") or [])
        successful = [obs for obs in state.get("observations") or [] if obs.status == "OK"]
        incomplete = [obs for obs in state.get("observations") or [] if obs.status != "OK"]
        if state.get("status") == "PARTIAL":
            status = "PARTIAL"
        elif not valid:
            status = "PARTIAL" if successful else "FAILED"
        elif successful and incomplete:
            status = "PARTIAL"
        elif successful:
            status = "COMPLETED"
        else:
            status = "FAILED"
        return {
            "status": status,
            "warnings": [*(state.get("warnings") or []), *failures],
            "trace": _trace(
                state, "critic", "CRITIC_PASS" if valid else "CRITIC_FAIL", status=status
            ),
        }

    def synthesize(self, state: LangGraphAgentState) -> dict[str, Any]:
        if state.get("status") in {"FAILED", "NEEDS_CLARIFICATION"}:
            return {
                "synthesis_draft": None, "synthesis_valid": False,
                "trace": _trace(state, "synthesize", "SKIP", status=state.get("status")),
            }
        if self.planner.llm_client is None:
            return {
                "synthesis_draft": None, "synthesis_valid": False,
                "trace": _trace(state, "synthesize", "SKIP", status="LLM_DISABLED"),
            }
        if state.get("llm_call_count", 0) >= state.get("max_llm_calls", 5):
            return {
                "synthesis_draft": None, "synthesis_valid": False,
                "warnings": [*(state.get("warnings") or []), "AGENT_MAX_LLM_CALLS_REACHED"],
                "status": "PARTIAL" if state.get("evidence") else "FAILED",
                "trace": _trace(state, "synthesize", "FALLBACK", status="MAX_LLM_CALLS"),
            }
        limitations = [
            f"{observation.metric or observation.tool}: {observation.status}"
            for observation in state.get("observations") or []
            if observation.status != "OK"
        ]
        limitations.extend(
            f"Nguồn bên ngoài mâu thuẫn về {item.get('claim_key')}; ưu tiên nguồn chính thức khi có."
            for item in state.get("source_conflicts") or []
        )
        try:
            draft = self.synthesizer.synthesize(
                state["question"], state.get("normalized_evidence") or [], limitations,
                analysis={
                    "financial_analysis_result": state.get("financial_analysis_result"),
                    "financial_signals": state.get("financial_signals"),
                    "benchmark_result": state.get("benchmark_result"),
                    "risk_review": state.get("risk_review"),
                    "analyst_report": state.get("analyst_report"),
                },
            )
            return {
                "synthesis_draft": draft, "synthesis_valid": False,
                "llm_call_count": state.get("llm_call_count", 0) + 1,
                "trace": _trace(
                    state, "synthesize", "LLM_SYNTHESIS_USED", status="STRUCTURED"
                ),
            }
        except Exception as exc:
            return {
                "synthesis_draft": None, "synthesis_valid": False,
                "llm_call_count": state.get("llm_call_count", 0) + 1,
                "warnings": [
                    *(state.get("warnings") or []),
                    f"LLM_SYNTHESIS_FAILURE:{type(exc).__name__}",
                ],
                "trace": _trace(state, "synthesize", "FALLBACK", status="LLM_FAILURE"),
            }

    def validate_synthesis(self, state: LangGraphAgentState) -> dict[str, Any]:
        draft = state.get("synthesis_draft")
        if draft is None:
            return {
                "synthesis_valid": False,
                "trace": _trace(state, "validate_synthesis", "SKIP", status="NO_DRAFT"),
            }
        observations = state.get("observations") or []
        web_only = bool(observations) and all(
            observation.tool == "web_search" for observation in observations
        )
        if web_only and state.get("web_sources"):
            # For external-only questions, Tavily results are the requested
            # evidence contract. The synthesis prompt already restricts the
            # model to retrieved content; do not reject an otherwise valid
            # structured response using the stricter financial-claim rules.
            return {
                "synthesis_valid": True,
                "trace": _trace(
                    state, "validate_synthesis", "CRITIC_PASS", status="WEB_GROUNDED"
                ),
            }
        allowed_tickers = set(state.get("tickers") or [])
        allowed_tickers.update(
            str(item.get("ticker")) for item in state.get("normalized_evidence") or []
            if item.get("ticker")
        )
        allowed_years = {
            int(item.get("year")) for item in state.get("normalized_evidence") or []
            if isinstance(item.get("year"), int)
        }
        valid, failures = self.synthesis_validator.validate(
            draft, state.get("normalized_evidence") or [],
            state.get("observations") or [], allowed_tickers, allowed_years,
        )
        if state.get("source_conflicts") and not any(
            cue in normalize_text(" ".join(draft.limitations))
            for cue in ("mau thuan", "khac biet", "khong thong nhat")
        ):
            valid = False
            failures.append("SOURCE_CONFLICT_NOT_DISCLOSED")
        regenerated = None
        regeneration_warning = None
        extra_llm_call = 0
        if (
            not valid
            and self.planner.llm_client is not None
            and state.get("llm_call_count", 0) < state.get("max_llm_calls", 5)
        ):
            extra_llm_call = 1
            try:
                regenerated = self.synthesizer.synthesize(
                    state["question"], state.get("normalized_evidence") or [],
                    ["Bản nháp trước bị từ chối: " + ", ".join(failures)],
                )
                valid, failures = self.synthesis_validator.validate(
                    regenerated, state.get("normalized_evidence") or [],
                    state.get("observations") or [], allowed_tickers, allowed_years,
                )
                if state.get("source_conflicts") and not any(
                    cue in normalize_text(" ".join(regenerated.limitations))
                    for cue in ("mau thuan", "khac biet", "khong thong nhat")
                ):
                    valid = False
                    failures.append("SOURCE_CONFLICT_NOT_DISCLOSED")
            except Exception as exc:
                regeneration_warning = f"LLM_SYNTHESIS_REGEN_FAILURE:{type(exc).__name__}"
                valid = False
        return {
            "synthesis_draft": regenerated if valid and regenerated is not None else draft,
            "synthesis_valid": valid,
            "llm_call_count": state.get("llm_call_count", 0) + extra_llm_call,
            "warnings": [
                *(state.get("warnings") or []),
                *([] if valid else ["AGENT_SYNTHESIS_REJECTED", *failures]),
                *([regeneration_warning] if regeneration_warning else []),
            ],
            "trace": _trace(
                state, "validate_synthesis", "CRITIC_PASS" if valid else "SYNTHESIS_REJECTED",
                status="GROUNDED" if valid else "DETERMINISTIC_FALLBACK",
            ),
        }

    def compose(self, state: LangGraphAgentState) -> dict[str, Any]:
        status = state.get("status", "FAILED")
        if state.get("external_research_required") and not state.get("web_sources"):
            answer = "Dữ liệu hiện tại chưa đủ để trả lời"
        elif status == "NEEDS_CLARIFICATION":
            missing = ", ".join(state.get("missing_information") or ["thông tin bắt buộc"])
            answer = f"FinSight cần bạn cung cấp thêm: {missing}."
        elif state.get("synthesis_valid") and state.get("synthesis_draft") is not None:
            answer = state["synthesis_draft"].render()
        else:
            sections: list[str] = []
            for index, (call, result) in enumerate(
                zip(state.get("tool_calls") or [], state.get("results") or []), start=1
            ):
                plan = {
                    "status": "OK", "intent": call["query_type"],
                    "queries": [{"query_type": call["query_type"], "params": call["params"]}],
                    "entities": {}, "warnings": [], "errors": [],
                }
                response = compose_response(state["question"], plan, [result])
                sections.append(f"<li>{response['answer']}</li>")
            limitations = [
                (
                    "<li>Nguồn dữ liệu phù hợp hiện chưa khả dụng; FinSight không đủ "
                    "bằng chứng để kết luận từ nguồn này.</li>"
                    if observation.status == "TOOL_UNAVAILABLE"
                    else f"<li>{escape(str(observation.metric or observation.tool))}: "
                         f"{escape(str(observation.status))}</li>"
                )
                for observation in state.get("observations") or []
                if observation.status != "OK"
            ]
            evidence_html = "".join(sections) or "<li>Chưa có bằng chứng khả dụng.</li>"
            limitation_html = "".join(limitations) or (
                "<li>Không ghi nhận hạn chế dữ liệu trong các tool đã chạy.</li>"
            )
            analysis = deterministic_analytical_summary(
                state.get("observations") or [], state.get("analytical_concepts") or []
            )
            analytical_points = "".join(
                f"<li>{escape(item)}</li>" for item in analysis["evidence_points"]
            )
            concern_points = "".join(
                f"<li>Suy luận: {escape(item)}</li>" for item in analysis["concerns"]
            )
            external_sources = "".join(
                f"<li>{escape(str(source.get('title') or 'Nguồn bên ngoài'))} — "
                f"{escape(str(source.get('publisher') or source.get('domain') or ''))} "
                f"({escape(str(source.get('publication_date') or 'không rõ ngày'))}) — "
                f"<a href=\"{escape(str(source.get('url') or ''))}\">nguồn</a></li>"
                for source in state.get("web_sources") or []
            )
            conflict_points = "".join(
                f"<li>Nguồn có khác biệt về {escape(str(item.get('claim_key')))}; "
                "FinSight ưu tiên nguồn có độ tin cậy cao hơn và giữ nguyên cảnh báo.</li>"
                for item in state.get("source_conflicts") or []
            )
            report = state.get("analyst_report") or {}
            report_section = ""
            if report:
                report_items = [
                    report.get("executive_summary"),
                    report.get("financial_assessment"),
                    report.get("benchmark_summary"),
                ]
                report_lists = [
                    *(report.get("strengths") or []),
                    *(report.get("weaknesses") or []),
                    *(report.get("risks") or []),
                    *(report.get("unknowns") or []),
                ]
                report_section = (
                    "<section><h3>Báo cáo phân tích</h3><ul>"
                    + "".join(f"<li>{escape(str(item))}</li>" for item in report_items if item)
                    + "".join(f"<li>{escape(str(item))}</li>" for item in report_lists)
                    + f"</ul><p>Độ tin cậy: {escape(str(report.get('confidence') or 'LOW'))}; "
                      f"độ phủ evidence: {escape(str(report.get('evidence_coverage') or 'LIMITED'))}</p></section>"
                )
            answer = (
                f"<section><h3>Kết luận</h3><p>{escape(analysis['conclusion'])}</p></section>"
                f"<section><h3>Bằng chứng và xu hướng</h3><ul>{analytical_points}{evidence_html}</ul></section>"
                + (
                    f"<section><h3>Bối cảnh bên ngoài</h3><ul>{external_sources}</ul></section>"
                    if external_sources else ""
                )
                + (
                    f"<section><h3>Điểm cần lưu ý / Rủi ro</h3><ul>{concern_points}</ul></section>"
                    if concern_points else ""
                )
                + f"<section><h3>Hạn chế</h3><ul>{limitation_html}{conflict_points}</ul></section>"
                + report_section
            )
        return {
            "final_answer": answer,
            "trace": _trace(state, "compose", "FINAL", status=status),
        }
