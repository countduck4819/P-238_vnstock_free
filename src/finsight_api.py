"""Standalone, merge-friendly FastAPI boundary for the FinSight chatbot."""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from math import ceil
from threading import Lock
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from src.api.finsight_models import (
    FinSightErrorResponse,
    FinSightQueryRequest,
    FinSightQueryResponse,
    FinSightResponseData,
    FinSightResponseMeta,
)
from src.services.finsight_application import (
    FinSightApplication,
    build_default_application,
)

APP_NAME = "Trợ lý ảo FinSight"
logger = logging.getLogger(__name__)
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_RATE_LIMIT_REQUESTS = 8
DEFAULT_RATE_LIMIT_WINDOW_SECONDS = 60.0


class SlidingWindowRateLimiter:
    """Small process-local limiter; suitable for one FinSight API instance."""

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self.max_requests = max(1, max_requests)
        self.window_seconds = max(1.0, window_seconds)
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str) -> tuple[bool, int]:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            timestamps = self._requests[key]
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            if len(timestamps) >= self.max_requests:
                return False, max(1, ceil(timestamps[0] + self.window_seconds - now))
            timestamps.append(now)
            return True, 0


def _environment_number(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def _timeout_seconds() -> float:
    try:
        value = float(os.environ.get("FINSIGHT_REQUEST_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS
    return min(max(value, 1.0), 120.0)


def _api_payload(pipeline: dict[str, Any], request_id: str) -> FinSightQueryResponse:
    plan = pipeline["plan"]
    response = pipeline["response"]
    tickers = plan.get("entities", {}).get("tickers", [])
    return FinSightQueryResponse(
        data=FinSightResponseData(
            answer=response["answer"],
            symbol=tickers[0] if len(tickers) == 1 else None,
            intent=response["intent"],
            status=response["status"],
            sources=response["sources"],
            warnings=response["warnings"],
            errors=response["errors"],
            data_used=response["data_used"],
        ),
        meta=FinSightResponseMeta(
            request_id=request_id,
            plan_status=plan["status"],
            query_types=[query["query_type"] for query in plan.get("queries", [])],
            llm_used=response["llm_used"],
            response_mode=response["mode"],
        ),
    )


def _error(
    status: int,
    code: str,
    message: str,
    *,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    payload = FinSightErrorResponse(status=status, code=code, message=message)
    return JSONResponse(status_code=status, content=payload.model_dump(), headers=headers)


def create_app(
    *,
    service: FinSightApplication | Any | None = None,
    timeout_seconds: float | None = None,
    rate_limit_requests: int | None = None,
    rate_limit_window_seconds: float | None = None,
) -> FastAPI:
    active_service = service or build_default_application()
    request_timeout = timeout_seconds if timeout_seconds is not None else _timeout_seconds()
    request_limit = rate_limit_requests if rate_limit_requests is not None else int(
        _environment_number("FINSIGHT_RATE_LIMIT_REQUESTS", DEFAULT_RATE_LIMIT_REQUESTS)
    )
    rate_window = (
        rate_limit_window_seconds
        if rate_limit_window_seconds is not None
        else _environment_number(
            "FINSIGHT_RATE_LIMIT_WINDOW_SECONDS", DEFAULT_RATE_LIMIT_WINDOW_SECONDS
        )
    )
    limiter = SlidingWindowRateLimiter(request_limit, rate_window)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        close = getattr(active_service, "close", None)
        if callable(close):
            close()

    application = FastAPI(
        title=APP_NAME,
        description="Deterministic Vietnamese financial chatbot application boundary",
        version="1.0.0",
        lifespan=lifespan,
    )
    application.state.finsight_service = active_service
    application.state.request_timeout_seconds = request_timeout
    application.state.rate_limiter = limiter

    @application.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "app": APP_NAME}

    @application.get("/ready", tags=["system"])
    async def ready() -> dict[str, str]:
        return {"status": "ready", "app": APP_NAME}

    async def handle_query(body: FinSightQueryRequest, request: Request):
        request_id = str(uuid4())
        client_host = request.client.host if request.client else "unknown"
        limiter_key = f"user:{body.user_id}" if body.user_id is not None else f"ip:{client_host}"
        allowed, retry_after = limiter.check(limiter_key)
        if not allowed:
            return _error(
                429,
                "FINSIGHT_RATE_LIMITED",
                f"Bạn đang gửi câu hỏi quá nhanh. Vui lòng thử lại sau {retry_after} giây.",
                headers={"Retry-After": str(retry_after)},
            )
        try:
            pipeline = await asyncio.wait_for(
                run_in_threadpool(
                    active_service.answer,
                    body.question,
                    [message.model_dump() for message in body.history],
                ),
                timeout=request_timeout,
            )
            return _api_payload(pipeline, request_id)
        except TimeoutError:
            return _error(504, "FINSIGHT_TIMEOUT", "Trợ lý ảo FinSight xử lý quá thời gian cho phép.")
        except Exception as exc:
            logger.exception("FinSight request failed request_id=%s error=%s", request_id, type(exc).__name__)
            return _error(503, "FINSIGHT_UNAVAILABLE", "Trợ lý ảo FinSight tạm thời chưa thể xử lý yêu cầu.")

    application.post(
        "/api/v1/finsight/query",
        response_model=FinSightQueryResponse,
        responses={
            429: {"model": FinSightErrorResponse},
            503: {"model": FinSightErrorResponse},
            504: {"model": FinSightErrorResponse},
        },
        tags=["finsight"],
    )(handle_query)
    # Compatibility path matches the existing FinSight UI/NestJS request contract.
    application.post(
        "/api/ai-stock/ask",
        response_model=FinSightQueryResponse,
        responses={
            429: {"model": FinSightErrorResponse},
            503: {"model": FinSightErrorResponse},
            504: {"model": FinSightErrorResponse},
        },
        include_in_schema=False,
    )(handle_query)
    return application


app = create_app()
