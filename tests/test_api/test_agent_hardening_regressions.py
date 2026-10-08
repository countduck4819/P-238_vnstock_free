from src.services.agent_actions import PlannerAction
from src.services.evidence_fusion import EvidenceFusionNode


def test_company_knowledge_action_matches_query_tool_contract():
    action = PlannerAction(
        action="COMPANY_KNOWLEDGE", ticker="FPT", query_text="FPT kinh doanh gì"
    )
    assert action.to_params() == {
        "ticker": "FPT",
        "query": "FPT kinh doanh gì",
        "document_types": ["company_profile"],
        "top_k": 3,
    }


def test_fusion_keeps_ticker_separate_for_comparison():
    package = EvidenceFusionNode().fuse(postgres_evidence=[
        {"ticker": "FPT", "canonical_metric_code": "net_profit", "value": 10, "year": 2024},
        {"ticker": "MBB", "canonical_metric_code": "net_profit", "value": 20, "year": 2024},
    ])
    assert {(fact.ticker, fact.metric, fact.value) for fact in package.facts} == {
        ("FPT", "net_profit", 10), ("MBB", "net_profit", 20)
    }
    assert package.conflict is False


def test_external_candidate_marked_non_numerical_is_not_fact():
    package = EvidenceFusionNode().fuse(external_evidence=[
        {
            "ticker": "FPT", "metric": "net_profit", "value": "999", "year": 2024,
            "source": "https://example.com", "numerical_truth": False,
        }
    ])
    assert package.facts == []
    assert package.external_candidates[0]["numerical_truth"] is False
