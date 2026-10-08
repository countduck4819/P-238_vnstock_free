"""Evidence-bounded equity analysis over an EvidencePackage.

This layer does not call an LLM and never changes, recalculates or fabricates
values. Every FACT/INFERENCE statement carries references to package entries.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.services.evidence_fusion import EvidencePackage


class ClaimKind(StrEnum):
    FACT = "FACT"
    INFERENCE = "INFERENCE"
    UNKNOWN = "UNKNOWN"


class AnalysisStatement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: ClaimKind
    text: str = Field(min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def grounded_claim(self) -> AnalysisStatement:
        if self.kind != ClaimKind.UNKNOWN and not self.evidence_refs:
            raise ValueError("FACT and INFERENCE statements require evidence references")
        return self


class EquityAnalysisReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    executive_summary: list[AnalysisStatement] = Field(default_factory=list)
    financial_trend: list[AnalysisStatement] = Field(default_factory=list)
    business_quality: list[AnalysisStatement] = Field(default_factory=list)
    strength: list[AnalysisStatement] = Field(default_factory=list)
    risk: list[AnalysisStatement] = Field(default_factory=list)
    missing_information: list[AnalysisStatement] = Field(default_factory=list)
    confidence_score: str


class EquityAnalysisNode:
    """Produce a conservative report from one fused package."""

    def analyze(self, package: EvidencePackage | dict[str, Any]) -> EquityAnalysisReport:
        package = package if isinstance(package, EvidencePackage) else EvidencePackage.model_validate(package)
        facts: list[AnalysisStatement] = []
        trend: list[AnalysisStatement] = []
        quality: list[AnalysisStatement] = []
        strength: list[AnalysisStatement] = []
        risk: list[AnalysisStatement] = []
        missing: list[AnalysisStatement] = []
        fact_refs: list[str] = []
        for index, fact in enumerate(package.facts):
            ref = f"fact:{fact.metric}:{fact.year or 'undated'}"
            fact_refs.append(ref)
            period = f" năm {fact.year}" if fact.year else ""
            facts.append(AnalysisStatement(
                kind=ClaimKind.FACT,
                text=f"{fact.metric}{period} có giá trị {fact.value} theo nguồn {fact.source}.",
                evidence_refs=[ref],
            ))
            if fact.metric.lower() in {"revenue_growth", "profit_growth", "net_revenue_yoy_growth", "net_profit_yoy_growth"}:
                trend.append(AnalysisStatement(
                    kind=ClaimKind.FACT,
                    text=f"Đã ghi nhận bằng chứng cho chỉ tiêu xu hướng {fact.metric}.",
                    evidence_refs=[ref],
                ))
        for index, interpretation in enumerate(package.interpretations):
            ref = f"interpretation:{index}"
            quality.append(AnalysisStatement(
                kind=ClaimKind.FACT, text=interpretation.text, evidence_refs=[ref],
            ))
        if fact_refs:
            strength.append(AnalysisStatement(
                kind=ClaimKind.INFERENCE,
                text="Có bằng chứng định lượng được hợp nhất để phục vụ phân tích.",
                evidence_refs=fact_refs,
            ))
        if package.conflict:
            risk.append(AnalysisStatement(
                kind=ClaimKind.INFERENCE,
                text="Các nguồn có số liệu mâu thuẫn; cần xác minh trước khi kết luận.",
                evidence_refs=[f"conflict:{item.key}" for item in package.conflicts],
            ))
        for limitation in package.limitations:
            missing.append(AnalysisStatement(kind=ClaimKind.UNKNOWN, text=limitation))
        if not facts and not quality:
            executive = [AnalysisStatement(
                kind=ClaimKind.UNKNOWN,
                text="Chưa có bằng chứng đủ để đưa ra kết luận tài chính.",
            )]
        elif package.conflict:
            executive = [AnalysisStatement(
                kind=ClaimKind.INFERENCE,
                text="Có bằng chứng để phân tích nhưng tồn tại mâu thuẫn cần được làm rõ.",
                evidence_refs=[f"conflict:{item.key}" for item in package.conflicts],
            )]
        else:
            executive = [AnalysisStatement(
                kind=ClaimKind.INFERENCE,
                text="Phân tích chỉ dựa trên các bằng chứng đã được cung cấp trong package.",
                evidence_refs=fact_refs or [f"interpretation:{index}" for index, _ in enumerate(package.interpretations)],
            )]
        if not trend:
            trend.append(AnalysisStatement(kind=ClaimKind.UNKNOWN, text="Chưa có đủ bằng chứng chuỗi thời gian để kết luận xu hướng."))
        if not quality:
            quality.append(AnalysisStatement(kind=ClaimKind.UNKNOWN, text="Chưa có bằng chứng định tính về chất lượng kinh doanh."))
        if not strength:
            strength.append(AnalysisStatement(kind=ClaimKind.UNKNOWN, text="Chưa xác định được điểm mạnh từ package hiện có."))
        if not risk:
            risk.append(AnalysisStatement(kind=ClaimKind.UNKNOWN, text="Chưa có bằng chứng rủi ro cụ thể trong package."))
        if not missing:
            missing.append(AnalysisStatement(kind=ClaimKind.UNKNOWN, text="Không ghi nhận hạn chế bổ sung từ package."))
        return EquityAnalysisReport(
            executive_summary=executive, financial_trend=trend,
            business_quality=quality, strength=strength, risk=risk,
            missing_information=missing, confidence_score=package.confidence,
        )

