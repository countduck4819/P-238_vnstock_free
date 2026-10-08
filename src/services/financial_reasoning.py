"""Evidence-bounded financial reasoning over a fused package."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.services.evidence_fusion import EvidenceFusionNode, EvidencePackage


class ReasoningType(StrEnum):
    FACT = "FACT"
    INFERENCE = "INFERENCE"
    UNKNOWN = "UNKNOWN"
    RISK = "RISK"


class ReasoningStatement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1)
    type: ReasoningType
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: str

    @model_validator(mode="after")
    def require_reference_for_claim(self) -> ReasoningStatement:
        if self.type in {ReasoningType.FACT, ReasoningType.INFERENCE, ReasoningType.RISK} and not self.evidence_refs:
            raise ValueError(f"{self.type} requires evidence_refs")
        return self


class FinancialAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    executive_summary: list[ReasoningStatement] = Field(default_factory=list)
    financial_trend: list[ReasoningStatement] = Field(default_factory=list)
    profitability_analysis: list[ReasoningStatement] = Field(default_factory=list)
    business_quality: list[ReasoningStatement] = Field(default_factory=list)
    strengths: list[ReasoningStatement] = Field(default_factory=list)
    risks: list[ReasoningStatement] = Field(default_factory=list)
    unknowns: list[ReasoningStatement] = Field(default_factory=list)
    confidence_score: int = Field(ge=0, le=100)
    confidence_reasons: list[str] = Field(default_factory=list)


class FinancialReasoningEngine:
    """Generate conservative FACT/INFERENCE/UNKNOWN/RISK statements only."""

    def __init__(self, fusion: EvidenceFusionNode | None = None) -> None:
        self.fusion = fusion or EvidenceFusionNode()

    def analyze(self, package: EvidencePackage | dict[str, Any]) -> FinancialAnalysisResult:
        package = package if isinstance(package, EvidencePackage) else EvidencePackage.model_validate(package)
        refs = {
            f"fact:{fact.metric}:{fact.year or 'undated'}": fact
            for fact in package.facts
        }
        interpretation_refs = {
            f"interpretation:{index}": item
            for index, item in enumerate(package.interpretations)
        }
        by_metric: dict[str, list[tuple[str, Any]]] = {}
        for ref, fact in refs.items():
            by_metric.setdefault(fact.metric.lower(), []).append((ref, fact.value))
        facts = [ReasoningStatement(
            text=f"Có bằng chứng trực tiếp cho chỉ tiêu {fact.metric}.",
            type=ReasoningType.FACT, evidence_refs=[ref], confidence=fact.confidence,
        ) for ref, fact in refs.items()]
        trend: list[ReasoningStatement] = []
        profitability: list[ReasoningStatement] = []
        business: list[ReasoningStatement] = [
            ReasoningStatement(text=item.text, type=ReasoningType.FACT,
                               evidence_refs=[ref], confidence=item.confidence)
            for ref, item in interpretation_refs.items()
        ]
        strengths: list[ReasoningStatement] = []
        risks: list[ReasoningStatement] = []

        trend.extend(facts)
        self._growth_inferences(by_metric, trend)
        self._profitability_inferences(by_metric, profitability)
        if refs:
            strengths.append(ReasoningStatement(
                text="Có bằng chứng định lượng đã được hợp nhất để phân tích.",
                type=ReasoningType.INFERENCE, evidence_refs=list(refs), confidence="MEDIUM",
            ))
        if package.conflict:
            conflict_refs = [f"conflict:{item.key}" for item in package.conflicts]
            risks.append(ReasoningStatement(
                text="Các nguồn bằng chứng mâu thuẫn; chưa thể kết luận chắc chắn về chỉ tiêu liên quan.",
                type=ReasoningType.RISK, evidence_refs=conflict_refs, confidence="LOW",
            ))
        unknowns = [ReasoningStatement(
            text=limitation, type=ReasoningType.UNKNOWN, confidence="LOW",
        ) for limitation in package.limitations]
        if not unknowns:
            unknowns.append(ReasoningStatement(
                text="Không có hạn chế bổ sung được ghi nhận trong Evidence Package.",
                type=ReasoningType.UNKNOWN, confidence="HIGH",
            ))
        if not trend:
            trend.append(ReasoningStatement(
                text="UNKNOWN: Chưa có đủ evidence chuỗi thời gian để phân tích xu hướng.",
                type=ReasoningType.UNKNOWN, confidence="LOW",
            ))
        if not profitability:
            profitability.append(ReasoningStatement(
                text="UNKNOWN: Chưa có đủ evidence về khả năng sinh lời.",
                type=ReasoningType.UNKNOWN, confidence="LOW",
            ))
        if not business:
            business.append(ReasoningStatement(
                text="UNKNOWN: Chưa có evidence định tính về chất lượng kinh doanh.",
                type=ReasoningType.UNKNOWN, confidence="LOW",
            ))
        if not strengths:
            strengths.append(ReasoningStatement(
                text="UNKNOWN: Chưa xác định được điểm mạnh từ evidence hiện có.",
                type=ReasoningType.UNKNOWN, confidence="LOW",
            ))
        if not risks:
            risks.append(ReasoningStatement(
                text="UNKNOWN: Chưa xác định được rủi ro cụ thể từ evidence hiện có.",
                type=ReasoningType.UNKNOWN, confidence="LOW",
            ))
        score, reasons = self._confidence(package, refs, interpretation_refs)
        executive = self._executive(package, refs, interpretation_refs)
        return FinancialAnalysisResult(
            executive_summary=executive, financial_trend=trend,
            profitability_analysis=profitability, business_quality=business,
            strengths=strengths, risks=risks, unknowns=unknowns,
            confidence_score=score, confidence_reasons=reasons,
        )

    @staticmethod
    def _growth_inferences(by_metric: dict[str, list[tuple[str, Any]]], output: list[ReasoningStatement]) -> None:
        revenue = by_metric.get("revenue_growth") or by_metric.get("net_revenue_yoy_growth")
        profit = by_metric.get("profit_growth") or by_metric.get("net_profit_yoy_growth")
        margin = by_metric.get("net_margin") or by_metric.get("net_profit_margin")
        if revenue:
            output.append(ReasoningStatement(
                text="FACT: Evidence có chỉ tiêu tăng trưởng doanh thu.",
                type=ReasoningType.FACT, evidence_refs=[item[0] for item in revenue], confidence="MEDIUM",
            ))
        if profit:
            output.append(ReasoningStatement(
                text="FACT: Evidence có chỉ tiêu tăng trưởng lợi nhuận.",
                type=ReasoningType.FACT, evidence_refs=[item[0] for item in profit], confidence="MEDIUM",
            ))
        if revenue and profit and margin:
            refs = [item[0] for item in [*revenue, *profit, *margin]]
            numbers = [FinancialReasoningEngine._number(item[1]) for item in [revenue[0], profit[0], margin[0]]]
            if all(number is not None for number in numbers):
                if numbers[1] > numbers[0] and numbers[2] > 0:
                    output.append(ReasoningStatement(
                        text="Suy luận: Chất lượng tăng trưởng lợi nhuận có dấu hiệu cải thiện.",
                        type=ReasoningType.INFERENCE, evidence_refs=refs, confidence="MEDIUM",
                    ))
                elif numbers[0] > 0 and numbers[1] < 0:
                    output.append(ReasoningStatement(
                        text="Suy luận: Tăng trưởng doanh thu chưa chuyển hóa thành tăng trưởng lợi nhuận.",
                        type=ReasoningType.INFERENCE, evidence_refs=refs, confidence="MEDIUM",
                    ))

    @staticmethod
    def _profitability_inferences(by_metric: dict[str, list[tuple[str, Any]]], output: list[ReasoningStatement]) -> None:
        for metric in ("gross_margin", "operating_margin", "net_margin", "net_profit_margin", "roa", "roe"):
            if metric in by_metric:
                output.append(ReasoningStatement(
                    text=f"FACT: Evidence có chỉ tiêu khả năng sinh lời {metric}.",
                    type=ReasoningType.FACT, evidence_refs=[item[0] for item in by_metric[metric]], confidence="MEDIUM",
                ))

    @staticmethod
    def _number(value: Any) -> Decimal | None:
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return None

    @staticmethod
    def _confidence(package: EvidencePackage, facts: dict[str, Any], interpretations: dict[str, Any]) -> tuple[int, list[str]]:
        available = len(facts) + len(interpretations)
        missing = sum(1 for item in package.limitations if any(cue in item.lower() for cue in ("missing", "thiếu", "chưa có", "không có")))
        score = round(100 * available / (available + missing)) if available + missing else 0
        reasons = ["Financial metrics available"] if facts else ["Financial metrics missing"]
        if interpretations:
            reasons.append("Business context available")
        if missing:
            reasons.append("Evidence limitations present")
        if package.conflict:
            score = min(score, 69)
            reasons.append("Conflicting evidence present")
        return score, reasons

    @staticmethod
    def _executive(package: EvidencePackage, facts: dict[str, Any], interpretations: dict[str, Any]) -> list[ReasoningStatement]:
        if not facts and not interpretations:
            return [ReasoningStatement(text="UNKNOWN: Evidence Package không đủ dữ liệu để kết luận.", type=ReasoningType.UNKNOWN, confidence="LOW")]
        refs = [*facts, *interpretations]
        text = "Phân tích chỉ sử dụng evidence đã cung cấp; không bổ sung dữ liệu bên ngoài."
        return [ReasoningStatement(text=text, type=ReasoningType.INFERENCE, evidence_refs=refs, confidence=package.confidence)]
