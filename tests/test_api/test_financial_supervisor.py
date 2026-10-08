from src.services.agent_planner import should_use_agent
from src.services.financial_supervisor import FinancialAgentSupervisor, UnifiedFinancialQueryHandler


def test_supervisor_routes_natural_questions_without_question_specific_workflows():
    assert not should_use_agent("Doanh thu FPT năm 2022?")
    assert should_use_agent("FPT đang khỏe lên hay yếu đi?")
    assert should_use_agent("Tại sao lợi nhuận HPG giảm?")
    assert should_use_agent("ROE của VCB có tốt không?")
    assert should_use_agent("HPG có đang bị định giá rẻ không?")


def test_supervisor_and_handler_are_same_public_contract():
    assert issubclass(FinancialAgentSupervisor, UnifiedFinancialQueryHandler)
