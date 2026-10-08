import json

from src.services.agent_critic import AgentCritic
from src.services.agent_state import AgentState, Observation
from src.services.financial_agent import FinancialResearchAgent
from src.services.finsight_application import FinSightApplication


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate(self, system_prompt, user_prompt):
        self.calls.append((system_prompt, user_prompt))
        if self.responses:
            return self.responses.pop(0)
        return json.dumps({
            "decision": "COMPLETE", "reason": "enough", "actions": [],
            "missing_information": [],
        })


class FakeHarness:
    def __init__(self, statuses=None):
        self.calls = []
        self.statuses = statuses or {}

    def execute_query(self, query_type, params):
        self.calls.append((query_type, params))
        status = self.statuses.get((query_type, params.get("metric")), "OK")
        tool = {
            "FACT": "get_fact", "TIME_SERIES": "get_timeseries",
            "COMPARE": "compare", "RANK": "rank",
            "EVALUATION": "evaluate_stock",
            "COMPANY_KNOWLEDGE": "search_company_knowledge",
        }[query_type]
        source = "QDRANT" if query_type == "COMPANY_KNOWLEDGE" else "POSTGRESQL"
        ticker = params.get("ticker")
        metric = params.get("metric")
        year = params.get("year") or params.get("end_year") or 2024
        if query_type == "COMPANY_KNOWLEDGE":
            data = [{"ticker": ticker, "document_type": "company_profile", "text": "Hồ sơ FPT"}]
        elif status == "OK":
            data = [{
                "ticker": ticker or "FPT", "year": year,
                "canonical_metric_code": metric or "net_profit",
                "value": "100", "unit": "source_native_numeric", "status": "OK",
            }]
        elif status == "MISSING":
            data = [{
                "ticker": ticker, "year": year, "canonical_metric_code": metric,
                "value": None, "unit": "source_native_numeric", "status": "MISSING",
            }]
        else:
            data = []
        return {
            "tool": tool, "status": status, "ticker": ticker,
            "tickers": params.get("tickers", []), "metric": metric, "year": year,
            "period": {"start_year": params.get("start_year"), "end_year": params.get("end_year")}
            if query_type == "TIME_SERIES" else None,
            "source": source, "warnings": [], "errors": [], "data": data,
            "provenance": [],
        }

    def close(self):
        pass


def plan(goal, actions):
    return json.dumps({"goal": goal, "actions": actions, "missing_information": []})


def decision(value, actions=None):
    return json.dumps({
        "decision": value, "reason": "mock decision", "actions": actions or [],
        "missing_information": [],
    })


def evaluation_action():
    return {"action": "EVALUATION", "ticker": "FPT", "reason": "latest year"}


def trend(metric="net_profit"):
    return {
        "action": "TIME_SERIES", "ticker": "FPT", "metric": metric,
        "start_year": 2020, "end_year": 2024, "reason": "trend",
    }


def test_01_simple_fact_still_uses_deterministic_fast_path():
    llm = FakeLLM([])
    app = FinSightApplication(harness=FakeHarness(), llm_client=llm)
    results = [
        app.answer("Doanh thu FPT năm 2024"),
        app.answer("LNST MBB năm 2025"),
        app.answer("Top 5 ngân hàng theo tổng tài sản năm 2024"),
    ]
    assert results[0]["plan"]["intent"] == "FACT"
    assert results[1]["plan"]["intent"] == "FACT"
    assert results[2]["plan"]["intent"] == "RANK"
    assert all("agent_trace" not in result for result in results)
    assert llm.calls == []


def test_02_complex_analysis_enters_langgraph():
    llm = FakeLLM([plan("financial_health", [evaluation_action()]), decision("COMPLETE")])
    result = FinSightApplication(harness=FakeHarness(), llm_client=llm).answer(
        "Phân tích sức khỏe tài chính FPT 5 năm gần nhất"
    )
    nodes = [item["node"] for item in result["agent_trace"]]
    assert nodes[:3] == ["route_request", "interpret_goal", "plan"]
    assert "execute_tool" in nodes and "critic" in nodes and "compose" in nodes


def test_03_llm_structured_multi_step_plan_executes_in_order():
    llm = FakeLLM([
        plan("trend", [trend("net_revenue"), trend("net_profit")]),
        decision("CONTINUE"), decision("COMPLETE"),
    ])
    harness = FakeHarness()
    result = FinancialResearchAgent(harness, llm_client=llm).answer("Phân tích FPT từ 2020 đến 2024")
    assert [call[1]["metric"] for call in harness.calls] == ["net_revenue", "net_profit"]
    assert result["plan"]["iteration_count"] == 2


def test_04_validated_calls_use_existing_query_harness():
    llm = FakeLLM([plan("health", [trend("total_assets")]), decision("COMPLETE")])
    harness = FakeHarness()
    FinancialResearchAgent(harness, llm_client=llm).answer("Phân tích tài chính FPT từ 2020 đến 2024")
    assert harness.calls == [("TIME_SERIES", {
        "ticker": "FPT", "metric": "total_assets", "start_year": 2020, "end_year": 2024,
    })]


def test_05_observation_changes_next_action():
    llm = FakeLLM([
        plan("health", [evaluation_action()]),
        decision("REPLAN", [trend("net_profit")]), decision("COMPLETE"),
    ])
    harness = FakeHarness()
    FinancialResearchAgent(harness, llm_client=llm).answer("Phân tích FPT 5 năm gần nhất")
    assert [item[0] for item in harness.calls] == ["EVALUATION", "TIME_SERIES"]
    assert '"year": 2024' in llm.calls[1][1]
    assert '"status": "OK"' in llm.calls[1][1]


def test_06_unsupported_result_causes_safe_replan():
    llm = FakeLLM([
        plan("health", [trend("roa")]),
        decision("REPLAN", [trend("total_assets")]), decision("COMPLETE"),
    ])
    harness = FakeHarness({("TIME_SERIES", "roa"): "UNSUPPORTED_FOR_MVP"})
    result = FinancialResearchAgent(harness, llm_client=llm).answer("Phân tích FPT từ 2020 đến 2024")
    assert [call[1]["metric"] for call in harness.calls] == ["roa", "total_assets"]
    assert result["response"]["status"] == "PARTIAL"


def test_07_missing_value_remains_missing():
    llm = FakeLLM([
        plan("health", [trend("net_profit"), trend("total_assets")]),
        decision("CONTINUE"), decision("COMPLETE"),
    ])
    harness = FakeHarness({("TIME_SERIES", "net_profit"): "MISSING"})
    result = FinancialResearchAgent(harness, llm_client=llm).answer("Phân tích FPT từ 2020 đến 2024")
    missing = result["results"][0]["data"][0]
    assert missing["value"] is None
    assert missing["status"] == "MISSING"
    assert result["response"]["status"] == "PARTIAL"


def test_08_hallucinated_tool_name_is_rejected_before_execution():
    bad = json.dumps({
        "goal": "research", "actions": [{"action": "WEB_SEARCH", "ticker": "FPT"}],
        "missing_information": [],
    })
    harness = FakeHarness()
    result = FinancialResearchAgent(harness, llm_client=FakeLLM([bad])).answer("Phân tích FPT")
    assert all(query_type != "WEB_SEARCH" for query_type, _ in harness.calls)
    assert any("LLM_PLANNER_FAILURE" in warning for warning in result["response"]["warnings"])


def test_09_hallucinated_metric_is_rejected_before_execution():
    action = trend("invented_metric")
    harness = FakeHarness()
    result = FinancialResearchAgent(harness, llm_client=FakeLLM([plan("health", [action])])).answer(
        "Phân tích FPT từ 2020 đến 2024"
    )
    assert harness.calls == []
    assert "INVALID_METRIC" in result["response"]["warnings"]


def test_10_duplicate_action_is_prevented():
    duplicate = trend("net_profit")
    llm = FakeLLM([
        plan("trend", [duplicate, duplicate]), decision("CONTINUE"), decision("COMPLETE"),
    ])
    harness = FakeHarness()
    result = FinancialResearchAgent(harness, llm_client=llm).answer("Phân tích FPT từ 2020 đến 2024")
    assert len(harness.calls) == 1
    assert "DUPLICATE_ACTION" in result["response"]["warnings"]


def test_11_max_iteration_guard_terminates_graph():
    llm = FakeLLM([plan("trend", [trend("net_profit"), trend("total_assets")])])
    harness = FakeHarness()
    result = FinancialResearchAgent(harness, llm_client=llm, max_iterations=1).answer(
        "Phân tích FPT từ 2020 đến 2024"
    )
    assert len(harness.calls) == 1
    assert "AGENT_MAX_ITERATIONS_REACHED" in result["response"]["warnings"]


def test_12_critic_rejects_unsupported_numerical_claim():
    observation = Observation.from_result({
        "tool": "get_fact", "status": "UNSUPPORTED", "ticker": "FPT",
        "metric": "roe", "year": 2024, "source": "POSTGRESQL", "data": [],
    })
    state = AgentState(question="ROE FPT", observations=[observation])
    valid, _ = AgentCritic().validate_claim(
        {"ticker": "FPT", "metric": "roe", "year": 2024, "value": "10"}, state
    )
    assert valid is False


def test_13_qdrant_cannot_become_numerical_truth():
    observation = Observation.from_result({
        "tool": "get_fact", "status": "OK", "ticker": "FPT", "metric": "net_profit",
        "year": 2024, "source": "QDRANT",
        "data": [{"ticker": "FPT", "year": 2024, "canonical_metric_code": "net_profit", "value": "100"}],
    })
    state = AgentState(question="LNST FPT", observations=[observation])
    valid, _ = AgentCritic().validate_claim(
        {"ticker": "FPT", "metric": "net_profit", "year": 2024, "value": "100"}, state
    )
    assert valid is False


def test_14_useful_evidence_with_unsupported_path_returns_partial():
    llm = FakeLLM([
        plan("health", [trend("net_profit"), trend("roa")]),
        decision("CONTINUE"), decision("COMPLETE"),
    ])
    harness = FakeHarness({("TIME_SERIES", "roa"): "UNSUPPORTED_FOR_MVP"})
    result = FinancialResearchAgent(harness, llm_client=llm).answer("Phân tích FPT từ 2020 đến 2024")
    assert result["response"]["status"] == "PARTIAL"
    assert result["response"]["data_used"]


def test_15_missing_ticker_returns_needs_clarification_without_llm_or_tool():
    llm = FakeLLM([])
    harness = FakeHarness()
    result = FinancialResearchAgent(harness, llm_client=llm).answer(
        "Phân tích sức khỏe tài chính 5 năm gần nhất"
    )
    assert result["response"]["status"] == "NEEDS_CLARIFICATION"
    assert result["plan"]["missing_information"] == ["ticker"]
    assert harness.calls == [] and llm.calls == []


def test_16_llm_cannot_switch_to_unrequested_ticker():
    harness = FakeHarness()
    action = {"action": "EVALUATION", "ticker": "HPG", "reason": "invented ticker"}
    result = FinancialResearchAgent(harness, llm_client=FakeLLM([plan("health", [action])])).answer(
        "Phân tích sức khỏe tài chính FPT"
    )
    assert harness.calls == []
    assert "TICKER_NOT_GROUNDED_IN_REQUEST" in result["response"]["warnings"]


def test_17_llm_cannot_invent_unobserved_year():
    harness = FakeHarness()
    action = {
        "action": "FACT", "ticker": "FPT", "metric": "net_profit",
        "year": 2024, "reason": "invented year",
    }
    result = FinancialResearchAgent(harness, llm_client=FakeLLM([plan("health", [action])])).answer(
        "Phân tích sức khỏe tài chính FPT"
    )
    assert harness.calls == []
    assert "YEAR_NOT_GROUNDED_IN_REQUEST_OR_OBSERVATION" in result["response"]["warnings"]


def test_18_no_llm_configuration_keeps_safe_bounded_fallback():
    harness = FakeHarness()
    result = FinancialResearchAgent(harness).answer(
        "Phân tích sức khỏe tài chính FPT 5 năm gần nhất"
    )
    assert harness.calls[0][0] == "EVALUATION"
    follow_up_tools = [call[0] for call in harness.calls[1:]]
    assert follow_up_tools
    assert set(follow_up_tools) == {"TIME_SERIES"}
    queried_metrics = {params["metric"] for _, params in harness.calls[1:]}
    assert {"net_revenue", "net_profit", "total_assets"}.issubset(queried_metrics)
    assert result["response"]["mode"] == "LANGGRAPH_SAFE_FALLBACK"
    assert result["response"]["llm_call_count"] == 0


def test_19_recent_event_risk_without_web_returns_unknown_not_failed():
    result = FinancialResearchAgent(FakeHarness()).answer("Rủi ro gần đây của FPT?")
    assert result["response"]["intent"] == "RECENT_EVENT_RISK"
    assert result["response"]["status"] == "UNKNOWN"
    assert result["response"]["answer"] == "Dữ liệu hiện tại chưa đủ để trả lời"
