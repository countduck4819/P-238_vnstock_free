from src.services.chat_pipeline import contextualize_question
from src.services.intent_router import create_query_plan
from src.services.query_tools import QueryTools, configured_value
from src.services.response_composer import compose_response


def test_bottom_is_understood_as_ascending_rank():
    plan = create_query_plan(
        "Bottom 5 ngân hàng theo lợi nhuận sau thuế năm 2024."
    )

    assert plan["status"] == "OK"
    assert plan["intent"] == "RANK"
    assert plan["queries"][0]["params"] == {
        "metric": "net_profit",
        "year": 2024,
        "sector": "BANK",
        "limit": 5,
        "descending": False,
    }


def test_qdrant_settings_environment_values_are_used(monkeypatch):
    monkeypatch.setenv("QDRANT_URL", "https://cloud.example")
    monkeypatch.setenv("QDRANT_API_KEY", "secret-value")
    assert configured_value("QDRANT_URL") == "https://cloud.example"
    assert configured_value("QDRANT_API_KEY") == "secret-value"


def test_generic_stock_wording_routes_to_company_profile():
    for question, ticker in (
        ("Cổ phiếu LDG", "LDG"),
        ("Cố phiếu LDG", "LDG"),
        ("Tôi muốn hỏi về cổ phiếu MBB", "MBB"),
        ("Tôi muốn thông tin về cổ phiếu MBB", "MBB"),
    ):
        plan = create_query_plan(question)
        assert plan["status"] == "OK"
        assert plan["intent"] == "COMPANY_KNOWLEDGE"
        assert plan["queries"][0]["params"]["ticker"] == ticker
        assert plan["queries"][0]["params"]["document_types"] == ["company_profile"]


def test_stock_evaluation_routes_with_optional_year():
    latest = create_query_plan("Đánh giá cổ phiếu LDG")
    explicit = create_query_plan("Phân tích cổ phiếu MBB năm 2024")

    assert latest["status"] == "OK"
    assert latest["intent"] == "EVALUATION"
    assert latest["queries"][0] == {
        "query_type": "EVALUATION",
        "params": {"ticker": "LDG", "year": None},
    }
    assert explicit["intent"] == "EVALUATION"
    assert explicit["queries"][0]["params"] == {"ticker": "MBB", "year": 2024}


def test_evaluate_stock_uses_latest_available_year(monkeypatch):
    tools = QueryTools()
    monkeypatch.setattr(tools, "_latest_available_year", lambda ticker: 2024)
    monkeypatch.setattr(tools, "_has_data_for_year", lambda ticker, year: True)

    def fake_fact(ticker, metric, year):
        return {
            "status": "OK",
            "data": [{
                "ticker": ticker,
                "year": year,
                "canonical_metric_code": metric,
                "value": "1",
                "unit": "ratio" if "growth" in metric or metric in {"roa", "roe", "net_profit_margin"} else "source_native_numeric",
                "status": "OK",
            }],
        }

    monkeypatch.setattr(tools, "get_fact", fake_fact)
    result = tools.evaluate_stock("MBB")

    assert result["status"] == "OK"
    assert result["year"] == 2024
    assert result["ticker"] == "MBB"
    assert result["data"]
    assert result["warnings"][0] == "EVALUATION_YEAR_DEFAULTED_LATEST:2024"


def test_evaluation_response_lists_metrics_observations_and_disclaimer():
    plan = create_query_plan("Đánh giá cổ phiếu LDG")
    response = compose_response(
        "Đánh giá cổ phiếu LDG",
        plan,
        [{
            "tool": "evaluate_stock",
            "status": "OK",
            "ticker": "LDG",
            "year": 2024,
            "sector": "CORPORATE",
            "source": "POSTGRESQL",
            "warnings": ["EVALUATION_YEAR_DEFAULTED_LATEST:2024"],
            "errors": [],
            "data": [
                {
                    "ticker": "LDG",
                    "year": 2024,
                    "canonical_metric_code": "net_revenue",
                    "value": "100000000000",
                    "unit": "source_native_numeric",
                    "status": "OK",
                },
                {
                    "ticker": "LDG",
                    "year": 2024,
                    "canonical_metric_code": "net_revenue_yoy_growth",
                    "value": "0.1",
                    "unit": "ratio",
                    "status": "OK",
                },
            ],
        }],
    )

    assert response["status"] == "OK"
    assert response["intent"] == "EVALUATION"
    assert "năm gần nhất" in response["answer"]
    assert "Doanh thu thuần" in response["answer"]
    assert "tăng 10.00%" in response["answer"]
    assert "không phải khuyến nghị mua hoặc bán" in response["answer"]


def test_evaluation_follow_up_can_supply_the_year():
    history = [
        {"role": "user", "content": "Đánh giá cổ phiếu MBB"},
        {"role": "assistant", "content": "Đánh giá theo năm gần nhất."},
    ]

    effective, applied = contextualize_question("năm 2023", history)
    plan = create_query_plan(effective)

    assert applied is True
    assert plan["status"] == "OK"
    assert plan["intent"] == "EVALUATION"
    assert plan["queries"][0]["params"] == {"ticker": "MBB", "year": 2023}


def test_follow_up_slots_are_inherited_from_recent_user_turns():
    history = [
        {"role": "user", "content": "rank 5 BANK highest"},
        {"role": "assistant", "content": "Bạn muốn xếp hạng theo chỉ tiêu nào?"},
        {"role": "user", "content": "total_assets"},
        {"role": "assistant", "content": "Bạn muốn xem năm nào?"},
    ]

    effective, applied = contextualize_question("2024", history)
    plan = create_query_plan(effective)

    assert applied is True
    assert plan["status"] == "OK"
    assert plan["intent"] == "RANK"
    assert plan["queries"][0]["params"] == {
        "metric": "total_assets",
        "year": 2024,
        "sector": "BANK",
        "limit": 5,
        "descending": True,
    }


def test_rank_limit_is_read_when_number_precedes_company_group():
    plan = create_query_plan(
        "Xếp hạng doanh thu thuần của 5 doanh nghiệp thường năm 2024"
    )

    assert plan["status"] == "OK"
    assert plan["queries"][0]["params"]["limit"] == 5


def test_follow_up_can_override_previous_rank_limit():
    history = [
        {
            "role": "user",
            "content": "Xếp hạng doanh thu thuần của doanh nghiệp thường năm 2024",
        },
        {"role": "assistant", "content": "Đây là 10 doanh nghiệp."},
    ]

    effective, applied = contextualize_question("chỉ cần 5 doanh nghiệp thôi", history)
    plan = create_query_plan(effective)

    assert applied is True
    assert plan["status"] == "OK"
    assert plan["queries"][0]["params"]["limit"] == 5


def test_complete_fact_does_not_inherit_an_old_bank_ranking_context():
    history = [
        {
            "role": "user",
            "content": "Xếp hạng 5 ngân hàng theo tổng tài sản năm 2024",
        },
        {"role": "assistant", "content": "Kết quả xếp hạng."},
    ]

    effective, applied = contextualize_question("Tổng nợ phải trả của FPT", history)
    plan = create_query_plan(effective)

    assert applied is False
    assert plan["intent"] == "FACT"
    assert plan["entities"]["tickers"] == ["FPT"]
    assert plan["entities"]["metrics"] == ["total_liabilities"]
    assert plan["errors"][0]["code"] == "MISSING_YEAR"


def test_year_follow_up_uses_the_most_recent_complete_fact_not_older_rank():
    history = [
        {
            "role": "user",
            "content": "Xếp hạng 5 ngân hàng theo tổng tài sản năm 2024",
        },
        {"role": "assistant", "content": "Kết quả xếp hạng."},
        {"role": "user", "content": "Tổng nợ phải trả của FPT"},
        {"role": "assistant", "content": "Bạn muốn xem năm nào?"},
    ]

    effective, applied = contextualize_question("năm 2024", history)
    plan = create_query_plan(effective)

    assert applied is True
    assert plan["status"] == "OK"
    assert plan["intent"] == "FACT"
    assert plan["queries"][0]["params"] == {
        "ticker": "FPT",
        "metric": "total_liabilities",
        "year": 2024,
    }


def test_finsight_capabilities_question_routes_to_greeting():
    plan = create_query_plan("FinSight có thể giúp tôi những gì?")

    assert plan["status"] == "OK"
    assert plan["intent"] == "GREETING"


def test_company_activity_wording_routes_to_company_knowledge():
    plan = create_query_plan("HPG hoạt động trong những lĩnh vực nào?")

    assert plan["status"] == "OK"
    assert plan["intent"] == "COMPANY_KNOWLEDGE"
    assert plan["queries"][0]["params"]["document_types"] == ["company_profile"]


def test_bank_fee_and_commission_wording_routes_to_fact():
    plan = create_query_plan(
        "Thu nhập phí và hoa hồng thuần của ACB năm 2024 là bao nhiêu?"
    )

    assert plan["status"] == "OK"
    assert plan["queries"][0]["params"]["metric"] == "net_fee_and_commission_income"


def test_growth_without_percent_word_still_routes_to_yoy_growth():
    plan = create_query_plan(
        "Lợi nhuận sau thuế HPG năm 2024 tăng bao nhiêu so với năm 2023?"
    )

    assert plan["status"] == "OK"
    assert plan["intent"] == "FACT"
    assert plan["queries"][0]["params"] == {
        "ticker": "HPG",
        "metric": "net_profit_yoy_growth",
        "year": 2024,
    }


def test_company_activity_and_fact_routes_to_hybrid():
    plan = create_query_plan(
        "HPG hoạt động trong lĩnh vực nào và lợi nhuận sau thuế năm 2024 ra sao?"
    )

    assert plan["status"] == "OK"
    assert plan["intent"] == "HYBRID"
    assert [query["query_type"] for query in plan["queries"]] == [
        "COMPANY_KNOWLEDGE",
        "FACT",
    ]


def test_company_information_and_fact_routes_to_hybrid():
    plan = create_query_plan(
        "Thông tin doanh nghiệp VCB và lợi nhuận trước thuế năm 2024."
    )

    assert plan["status"] == "OK"
    assert plan["intent"] == "HYBRID"


def test_bare_ranking_defaults_to_descending_with_warning():
    plan = create_query_plan(
        "Xếp hạng 7 doanh nghiệp theo tổng tài sản năm 2024."
    )

    assert plan["status"] == "OK"
    assert plan["queries"][0]["params"]["descending"] is True
    assert plan["queries"][0]["params"]["limit"] == 7
    assert plan["warnings"] == ["RANK_DIRECTION_DEFAULTED_DESC"]


def test_clarification_explains_what_is_missing():
    plan = create_query_plan("So sánh lợi nhuận FPT năm 2024.")
    response = compose_response("", plan, [])

    assert response["status"] == "NEEDS_CLARIFICATION"
    assert "ít nhất hai mã" in response["answer"]


def test_derived_rank_limit_is_explained():
    plan = {"status": "OK", "intent": "RANK", "errors": [], "warnings": []}
    result = {
        "status": "UNSUPPORTED_FOR_MVP",
        "metric": "roe",
        "errors": [{"code": "UNSUPPORTED_FOR_MVP", "message": "not materialized"}],
        "warnings": [],
    }
    response = compose_response("", plan, [result])

    assert response["status"] == "UNSUPPORTED_FOR_MVP"
    assert "chưa được tính sẵn" in response["answer"]
    assert "giữa các mã cụ thể" in response["answer"]


def test_greeting_is_local_and_does_not_need_a_query():
    question = "Xin chào, bạn là trợ lý gì?"
    plan = create_query_plan(question)
    response = compose_response(question, plan, [])

    assert plan["status"] == "OK"
    assert plan["intent"] == "GREETING"
    assert plan["queries"] == []
    assert response["status"] == "OK"
    assert response["llm_used"] is False
    assert "Trợ lý ảo FinSight" in response["answer"]
    assert "báo cáo tài chính" in response["answer"]


def test_greeting_with_a_financial_request_stays_financial():
    plan = create_query_plan("Xin chào, doanh thu FPT năm 2024 là bao nhiêu?")

    assert plan["intent"] == "FACT"
    assert plan["queries"][0]["query_type"] == "FACT"


def test_gibberish_does_not_inherit_previous_financial_context():
    history = [
        {"role": "user", "content": "Doanh thu HPG năm 2023"},
        {"role": "assistant", "content": "Doanh thu thuần của HPG..."},
    ]

    effective, applied = contextualize_question("ibhreir", history)
    plan = create_query_plan(effective)
    response = compose_response(effective, plan, [])

    assert effective == "ibhreir"
    assert applied is False
    assert plan["errors"][0]["code"] == "GIBBERISH_OR_UNSUPPORTED"
    assert "Trợ lý ảo FinSight" in response["answer"]
    assert "Doanh thu của FPT năm 2024" in response["answer"]


def test_compound_fact_then_rank_is_planned_and_composed_in_order():
    question = (
        "Lợi nhuận sau thuế của MBB năm 2024 là bao nhiêu và hãy xếp hạng "
        "5 ngân hàng có lợi nhuận sau thuế năm 2024"
    )
    plan = create_query_plan(question)

    assert plan["status"] == "OK"
    assert plan["intent"] == "MULTI_QUERY"
    assert plan["queries"] == [
        {
            "query_type": "FACT",
            "params": {"ticker": "MBB", "metric": "net_profit", "year": 2024},
        },
        {
            "query_type": "RANK",
            "params": {
                "metric": "net_profit",
                "year": 2024,
                "sector": "BANK",
                "limit": 5,
                "descending": True,
            },
        },
    ]

    fact_row = {
        "ticker": "MBB", "year": 2024, "canonical_metric_code": "net_profit",
        "value": "22951260000000", "unit": "source_native_numeric", "status": "OK",
    }
    rank_rows = [
        {
            "ticker": ticker, "year": 2024, "canonical_metric_code": "net_profit",
            "value": value, "unit": "source_native_numeric", "status": "OK",
        }
        for ticker, value in (("VCB", "33853120000000"), ("MBB", "22951260000000"))
    ]
    response = compose_response(
        question,
        plan,
        [
            {"status": "OK", "source": "POSTGRESQL", "data": [fact_row], "errors": [], "warnings": []},
            {"status": "OK", "source": "POSTGRESQL", "data": rank_rows, "errors": [], "warnings": []},
        ],
    )

    assert response["intent"] == "MULTI_QUERY"
    assert response["status"] == "OK"
    assert response["answer"].index("MBB") < response["answer"].index("Xếp hạng")
    assert response["answer"].count("Kết quả") == 2


def test_compound_wording_doanh_thu_sau_thue_is_supported_for_banks():
    plan = create_query_plan(
        "Doanh thu sau thuế của MBB năm 2024 là bao nhiêu và hãy xếp hạng "
        "3 ngân hàng có lợi nhuận cao nhất năm 2023"
    )

    assert plan["status"] == "OK"
    assert [query["query_type"] for query in plan["queries"]] == ["FACT", "RANK"]
    assert plan["queries"][0]["params"] == {
        "ticker": "MBB", "metric": "net_profit", "year": 2024,
    }
    assert plan["queries"][1]["params"]["year"] == 2023
    assert plan["queries"][1]["params"]["limit"] == 3


def test_three_explicit_requests_create_three_ordered_subplans():
    plan = create_query_plan(
        "Doanh thu FPT năm 2024; lợi nhuận sau thuế FPT năm 2024; "
        "xếp hạng 5 doanh nghiệp theo lợi nhuận sau thuế năm 2024"
    )

    assert plan["status"] == "OK"
    assert plan["intent"] == "MULTI_QUERY"
    assert [query["query_type"] for query in plan["queries"]] == ["FACT", "FACT", "RANK"]


def test_single_ticker_compare_two_years_routes_to_timeseries():
    plan = create_query_plan("So sánh doanh thu thuần của FPT năm 2022 và 2023")

    assert plan["status"] == "OK"
    assert plan["intent"] == "TIME_SERIES"
    assert plan["queries"][0] == {
        "query_type": "TIME_SERIES",
        "params": {
            "ticker": "FPT",
            "metric": "net_revenue",
            "start_year": 2022,
            "end_year": 2023,
        },
    }


def test_explicit_revenue_growth_between_consecutive_years_routes_to_fact():
    plan = create_query_plan(
        "Tăng trưởng doanh thu FPT năm 2023 so với năm 2022 là bao nhiêu?"
    )

    assert plan["status"] == "OK"
    assert plan["intent"] == "FACT"
    assert plan["queries"][0] == {
        "query_type": "FACT",
        "params": {
            "ticker": "FPT",
            "metric": "net_revenue_yoy_growth",
            "year": 2023,
        },
    }


def test_percent_wording_promotes_revenue_to_growth_metric():
    plan = create_query_plan(
        "Doanh thu FPT năm 2023 tăng bao nhiêu phần trăm so với năm 2022?"
    )

    assert plan["status"] == "OK"
    assert plan["intent"] == "FACT"
    assert plan["queries"][0]["params"] == {
        "ticker": "FPT",
        "metric": "net_revenue_yoy_growth",
        "year": 2023,
    }


def test_growth_response_lists_both_revenues_before_growth_result():
    plan = {"status": "OK", "intent": "FACT", "errors": [], "warnings": []}
    result = {
        "status": "OK",
        "metric": "net_revenue_yoy_growth",
        "ticker": "FPT",
        "year": 2023,
        "source": "POSTGRESQL_DERIVED",
        "warnings": [],
        "data": [{
            "ticker": "FPT",
            "year": 2023,
            "canonical_metric_code": "net_revenue_yoy_growth",
            "value": "0.20",
            "unit": "ratio",
            "calculation_status": "OK",
            "input_metrics": [
                {"metric": "net_revenue", "year": 2023, "value": "120000000000"},
                {"metric": "net_revenue", "year": 2022, "value": "100000000000"},
            ],
        }],
    }

    response = compose_response("", plan, [result])

    answer = response["answer"]
    assert answer.index("năm 2022") < answer.index("năm 2023") < answer.index("tăng 20.00%")
    assert "100,00 tỷ đồng" in answer
    assert "120,00 tỷ đồng" in answer
    assert response["llm_used"] is False


def test_missing_fact_names_requested_ticker_year_and_metric():
    plan = {"status": "OK", "intent": "FACT", "errors": [], "warnings": []}
    result = {
        "status": "MISSING",
        "metric": "net_revenue",
        "ticker": "FPT",
        "year": 2025,
        "source": "POSTGRESQL",
        "warnings": [],
        "errors": [],
        "data": [],
    }

    response = compose_response("Doanh thu FPT năm 2025", plan, [result])

    assert response["status"] == "MISSING"
    assert response["answer"] == (
        "Hiện FinSight chưa có dữ liệu năm 2025 của mã FPT "
        "cho chỉ tiêu doanh thu thuần."
    )
    assert response["llm_used"] is False


def test_management_response_is_complete_and_uses_officer_roles():
    plan = {"status": "OK", "intent": "COMPANY_KNOWLEDGE", "errors": [], "warnings": []}
    result = {
        "status": "OK",
        "source": "QDRANT_QUALITATIVE",
        "warnings": [],
        "data": [{
            "ticker": "FPT",
            "document_id": "management-fpt",
            "document_type": "management",
            "text": (
                "Mã cổ phiếu: FPT\n"
                "Tổng giám đốc: Mr. Trương Gia Bình\n"
                "Chức vụ CEO: Chủ tịch HĐQT\n"
                "Ban lãnh đạo: Ông Trương Gia Bình | CTHĐQT | CTHĐQT (Chairman of BOD) | 1988; "
                "Ông Nguyễn Văn Khoa | TGĐ | TGĐ (CEO) | 2019; "
                "Ông Hoàng Hữu Chiến | KTT | KTT (Chief Accountant) | 2010"
            ),
            "source_files": ["officers.json"],
            "source_provider": "vnstock_vci",
            "as_of_date": "2025-12-31T00:00:00",
            "score": 0.9,
        }],
    }

    response = compose_response("Ban lãnh đạo FPT gồm những ai?", plan, [result])

    assert response["status"] == "OK"
    assert response["llm_used"] is False
    assert "Ông Trương Gia Bình</b> – Chủ tịch HĐQT" in response["answer"]
    assert "Ông Nguyễn Văn Khoa</b> – Tổng giám đốc" in response["answer"]
    assert "Ông Hoàng Hữu Chiến</b> – Kế toán trưởng" in response["answer"]
    assert "Mr. Trương Gia Bình" not in response["answer"]
    assert response["answer"].endswith("</ul>")


def test_management_year_filters_by_role_start_year_and_explains_semantics():
    plan = {"status": "OK", "intent": "COMPANY_KNOWLEDGE", "errors": [], "warnings": []}
    result = {
        "status": "OK",
        "source": "QDRANT_QUALITATIVE",
        "warnings": [],
        "data": [{
            "ticker": "FPT",
            "document_id": "management-fpt",
            "document_type": "management",
            "text": (
                "Mã cổ phiếu: FPT\nBan lãnh đạo: "
                "Ông Trương Gia Bình | CTHĐQT | CTHĐQT (Chairman of BOD) | 1988; "
                "Ông Nguyễn Văn Khoa | TGĐ | TGĐ (CEO) | 2019; "
                "Ông Phạm Minh Tuấn | Phó TGĐ | Phó TGĐ (Deputy CEO) | 2024"
            ),
            "source_files": ["officers.json"],
            "source_provider": "vnstock_vci",
            "as_of_date": "2025-12-31T00:00:00",
            "score": 0.9,
        }],
    }

    response = compose_response("Ban lãnh đạo của FPT năm 2024", plan, [result])

    assert "Ông Phạm Minh Tuấn" in response["answer"]
    assert "Ông Trương Gia Bình" not in response["answer"]
    assert "Ông Nguyễn Văn Khoa" not in response["answer"]
    assert "năm bắt đầu chức vụ" in response["answer"]


def test_rank_wording_preserves_backend_order_and_values():
    plan = {"status": "OK", "intent": "RANK", "errors": [], "warnings": []}
    result = {
        "status": "OK",
        "metric": "total_assets",
        "year": 2024,
        "sector": "BANK",
        "source": "POSTGRESQL",
        "warnings": [],
        "data": [
            {
                "ticker": "AAA",
                "year": 2024,
                "canonical_metric_code": "total_assets",
                "value": "2000000000",
                "unit": "source_native_numeric",
                "status": "OK",
            },
            {
                "ticker": "BBB",
                "year": 2024,
                "canonical_metric_code": "total_assets",
                "value": "1000000000",
                "unit": "source_native_numeric",
                "status": "OK",
            },
        ],
    }
    response = compose_response("", plan, [result])

    assert response["answer"].startswith("<p>Xếp hạng tổng tài sản trong nhóm ngân hàng")
    assert "<b>1. AAA</b>" in response["answer"]
    assert "<b>2. BBB</b>" in response["answer"]
    assert response["answer"].index("AAA") < response["answer"].index("BBB")
    assert [row["raw_value"] for row in response["data_used"]] == [
        "2000000000",
        "1000000000",
    ]
