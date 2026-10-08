"""Public API contracts for the FinSight chatbot boundary."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FinSightConversationMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class FinSightQueryRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    question: str = Field(min_length=1, max_length=1000)
    user_id: int | None = Field(default=None, alias="userId", ge=1)
    history: list[FinSightConversationMessage] = Field(default_factory=list, max_length=12)

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("question must not be blank")
        return normalized


class FinSightResponseData(BaseModel):
    answer: str
    symbol: str | None = None
    intent: str
    status: str
    sources: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    data_used: list[dict[str, Any]] = Field(default_factory=list)


class FinSightResponseMeta(BaseModel):
    request_id: str
    plan_status: str
    query_types: list[str] = Field(default_factory=list)
    llm_used: bool
    response_mode: str


class FinSightQueryResponse(BaseModel):
    app: str = "Trợ lý ảo FinSight"
    status: int = 200
    code: str = "SUCCESS"
    message: str = "Trợ lý ảo FinSight trả lời thành công"
    data: FinSightResponseData
    meta: FinSightResponseMeta


class FinSightErrorResponse(BaseModel):
    app: str = "Trợ lý ảo FinSight"
    status: int
    code: str
    message: str
