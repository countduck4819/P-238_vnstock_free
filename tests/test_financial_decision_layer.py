from src.services.financial_decision_layer import FinancialAnalystDecisionLayer


def _obs(ticker, metric, values):
    return type("Observation", (), {
        "status": "OK", "metric": metric, "ticker": ticker,
        "data": [{"ticker": ticker, "canonical_metric_code": metric, "value": value}
                 for value in values],
    })()


def test_classifies_valuation_and_requires_valuation_evidence():
    layer = FinancialAnalystDecisionLayer()
    decision = layer.classify("HPG có đang bị định giá rẻ không?")
    assert decision.intent == "VALUATION_ANALYSIS"
    assert "pe" in decision.required_evidence


def test_splits_financial_statement_and_recent_event_risk():
    layer = FinancialAnalystDecisionLayer()
    assert layer.classify("Nợ vay của FPT có cao không?").intent == "FINANCIAL_STATEMENT_RISK"
    recent = layer.classify("Rủi ro gần đây của FPT?")
    assert recent.intent == "RECENT_EVENT_RISK"
    assert recent.external_required


def test_health_conclusion_is_explicit_when_revenue_and_profit_grow():
    layer = FinancialAnalystDecisionLayer()
    state = {"observations": [_obs("FPT", "net_revenue", [100, 120]),
                               _obs("FPT", "net_profit", [10, 15])]}
    answer = layer.enhance("FPT đang khỏe lên hay yếu đi?", state,
                           "<section><h3>Kết luận</h3><p>Xu hướng khác.</p></section>")
    assert "khỏe lên" in answer


def test_valuation_response_is_unknown_without_price_multiples():
    layer = FinancialAnalystDecisionLayer()
    state = {"evidence": [{"metric": "net_profit"}]}
    answer = layer.enhance("HPG có đang bị định giá rẻ không?", state, "ignored")
    assert "Chưa đủ dữ liệu" in answer
    assert "P/E" in answer


def test_health_reads_normalized_and_derived_evidence_and_returns_refs():
    layer = FinancialAnalystDecisionLayer()
    state = {
        "observations": [],
        "normalized_evidence": [
            {"metric": "net_revenue", "ticker": "FPT", "year": 2021, "value": 100, "evidence_id": "rev-21"},
            {"metric": "net_revenue", "ticker": "FPT", "year": 2024, "value": 140, "evidence_id": "rev-24"},
            {"metric": "net_profit", "ticker": "FPT", "year": 2021, "value": 10, "evidence_id": "profit-21"},
            {"metric": "net_profit", "ticker": "FPT", "year": 2024, "value": 18, "evidence_id": "profit-24"},
        ],
        "derived_metrics": [
            {"metric": "net_profit_margin", "ticker": "FPT", "year": 2021, "value": 0.10, "evidence_id": "margin-21"},
            {"metric": "net_profit_margin", "ticker": "FPT", "year": 2024, "value": 0.13, "evidence_id": "margin-24"},
        ],
        "compact_observations": [],
    }
    result = layer.health_assessment(state)
    assert "khỏe lên" in result["conclusion"]
    assert "rev-21" in result["evidence_refs"]


def test_comparison_balances_growth_margin_stability_and_missing_cashflow():
    layer = FinancialAnalystDecisionLayer()
    evidence = []
    values = {
        "FPT": {
            "net_profit_yoy_growth": [(2023, 0.20), (2024, 0.21), (2025, 0.19)],
            "net_profit_margin": [(2024, 0.15), (2025, 0.16)],
        },
        "HPG": {
            "net_profit_yoy_growth": [(2023, -0.20), (2024, 0.76), (2025, 0.29)],
            "net_profit_margin": [(2024, 0.09), (2025, 0.10)],
        },
    }
    for ticker, metrics in values.items():
        for metric, rows in metrics.items():
            for year, value in rows:
                evidence.append({
                    "ticker": ticker, "metric": metric, "year": year,
                    "value": value, "evidence_id": f"{ticker}-{metric}-{year}",
                })
    result = layer.comparison_assessment({"normalized_evidence": evidence})
    assert "HPG nổi bật hơn về tốc độ" in result["conclusion"]
    assert "FPT nổi bật hơn về biên" in result["conclusion"]
    assert any("dòng tiền" in item for item in result["limitations"])
    assert any("ổn định hơn" in item for item in result["strengths"]["FPT"])
    assert result["evidence_refs"]
