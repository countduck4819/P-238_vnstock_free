import time

import pytest
from httpx import ASGITransport, AsyncClient

from src.finsight_api import create_app


def pipeline_result() -> dict:
    return {
        "plan": {
            "status": "OK",
            "entities": {"tickers": ["FPT"]},
            "queries": [{"query_type": "FACT", "params": {}}],
        },
        "response": {
            "answer": "Doanh thu thuần của FPT là 1.234 tỷ đồng.",
            "intent": "FACT",
            "status": "OK",
            "sources": [{"source": "PostgreSQL"}],
            "warnings": [],
            "errors": [],
            "data_used": [{"ticker": "FPT"}],
            "llm_used": False,
            "mode": "deterministic",
        },
    }


class FakeService:
    def answer(self, question: str, history=None) -> dict:
        assert question == "Doanh thu FPT?"
        return pipeline_result()


class BrokenService:
    def answer(self, question: str, history=None) -> dict:
        raise RuntimeError("private backend details")


class SlowService:
    def answer(self, question: str, history=None) -> dict:
        time.sleep(0.05)
        return pipeline_result()


@pytest.mark.asyncio
async def test_finsight_health_and_query_contract():
    app = create_app(service=FakeService())
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        health = await client.get("/health")
        response = await client.post(
            "/api/v1/finsight/query",
            json={"userId": 7, "question": "  Doanh thu FPT?  "},
        )

    assert health.json() == {"status": "ok", "app": "Trợ lý ảo FinSight"}
    assert response.status_code == 200
    payload = response.json()
    assert payload["app"] == "Trợ lý ảo FinSight"
    assert payload["data"]["answer"].startswith("Doanh thu")
    assert payload["data"]["symbol"] == "FPT"
    assert payload["meta"]["query_types"] == ["FACT"]
    assert payload["meta"]["llm_used"] is False


@pytest.mark.asyncio
async def test_existing_ui_compatibility_route():
    app = create_app(service=FakeService())
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/ai-stock/ask",
            json={"userId": 7, "question": "Doanh thu FPT?"},
        )

    assert response.status_code == 200
    assert response.json()["data"]["answer"]


@pytest.mark.asyncio
async def test_blank_question_is_rejected():
    app = create_app(service=FakeService())
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/finsight/query", json={"question": "   "}
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_backend_error_is_sanitized():
    app = create_app(service=BrokenService())
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/finsight/query", json={"question": "Doanh thu FPT?"}
        )

    assert response.status_code == 503
    assert response.json()["code"] == "FINSIGHT_UNAVAILABLE"
    assert "private backend details" not in response.text


@pytest.mark.asyncio
async def test_request_timeout_is_bounded():
    app = create_app(service=SlowService(), timeout_seconds=0.01)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/finsight/query", json={"question": "Doanh thu FPT?"}
        )

    assert response.status_code == 504
    assert response.json()["code"] == "FINSIGHT_TIMEOUT"


@pytest.mark.asyncio
async def test_rate_limit_returns_friendly_retry_response():
    app = create_app(
        service=FakeService(),
        rate_limit_requests=2,
        rate_limit_window_seconds=60,
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = await client.post(
            "/api/v1/finsight/query",
            json={"userId": 99, "question": "Doanh thu FPT?"},
        )
        second = await client.post(
            "/api/v1/finsight/query",
            json={"userId": 99, "question": "Doanh thu FPT?"},
        )
        limited = await client.post(
            "/api/v1/finsight/query",
            json={"userId": 99, "question": "Doanh thu FPT?"},
        )

    assert first.status_code == second.status_code == 200
    assert limited.status_code == 429
    assert limited.json()["code"] == "FINSIGHT_RATE_LIMITED"
    assert "thử lại sau" in limited.json()["message"]
    assert int(limited.headers["Retry-After"]) >= 1
