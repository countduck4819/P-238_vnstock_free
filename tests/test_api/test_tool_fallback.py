import json

from src.services.agent_actions import registered_tool
from src.services.financial_agent import FinancialResearchAgent
from src.services.query_harness import QueryHarness
from src.services.response_composer import compose_response


def test_registry_contains_only_registered_harness_tools():
    assert registered_tool("FACT") == "get_fact"
    assert registered_tool("COMPANY_KNOWLEDGE") == "search_company_knowledge"
    assert registered_tool("not_a_tool") is None
    assert "FACT" in QueryHarness.ROUTES


def test_unavailable_tool_is_not_exposed_in_public_answer():
    result = compose_response(
        "Doanh thu FPT năm 2024",
        {"status": "OK", "intent": "FACT"},
        [{
            "tool": "get_fact", "status": "TOOL_UNAVAILABLE", "ticker": "FPT",
            "metric": "net_revenue", "year": 2024, "data": [],
            "errors": [{"code": "TOOL_UNAVAILABLE", "message": "ConnectionError"}],
        }],
    )
    serialized = json.dumps(result, ensure_ascii=False)
    assert "TOOL_UNAVAILABLE" not in serialized
    assert "ConnectionError" not in serialized
    assert "chưa khả dụng" in result["answer"]


def test_graph_public_answer_hides_unavailable_status():
    class FailingHarness:
        def execute_query(self, query_type, params):
            raise ConnectionError("private database endpoint")

    result = FinancialResearchAgent(FailingHarness()).answer("Doanh thu FPT năm 2024")
    assert "TOOL_UNAVAILABLE" not in result["response"]["answer"]
    assert "private database endpoint" not in result["response"]["answer"]
