"""Deterministic risk review over reasoning, signals and benchmarks."""
from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.services.benchmark_engine import BenchmarkResult, Position
from src.services.financial_interpretation import FinancialSignalResult, SignalCategory, SignalDirection
from src.services.financial_reasoning import FinancialAnalysisResult


class RiskType(StrEnum):
    FINANCIAL = "FINANCIAL"
    EARNINGS_QUALITY = "EARNINGS_QUALITY"
    GROWTH = "GROWTH"
    BUSINESS = "BUSINESS"
    LEVERAGE = "LEVERAGE"
    LIQUIDITY = "LIQUIDITY"
    VALUATION = "VALUATION"


class RiskSeverity(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class RiskItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: RiskType
    severity: RiskSeverity
    direction: str
    statement: str = Field(min_length=1)
    evidence_refs: list[str] = Field(min_length=1)
    confidence: str

    @model_validator(mode="after")
    def validate_risk_scope(self) -> RiskItem:
        lowered = self.statement.lower()
        if any(term in lowered for term in ("phá sản", "pha san", "price target", "giá mục tiêu", "gia muc tieu", "mua/bán", "mua ban")):
            raise ValueError("Risk review cannot predict bankruptcy or issue trading advice")
        return self


class RiskReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    financial_analysis_result: FinancialAnalysisResult
    financial_signals: FinancialSignalResult
    benchmark_result: BenchmarkResult


class RiskReviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    overall_risk_level: RiskSeverity
    risks: list[RiskItem] = Field(default_factory=list)
    risk_summary: str
    unknown_risks: list[str] = Field(default_factory=list)
    confidence: int = Field(ge=0, le=100)


class RiskReviewEngine:
    """Review explicit negative signals without accessing any data source."""

    def review(self, payload: RiskReviewInput | dict[str, Any]) -> RiskReviewResult:
        request = payload if isinstance(payload, RiskReviewInput) else RiskReviewInput.model_validate(payload)
        risks: list[RiskItem] = []
        unknown: list[str] = []
        signals = request.financial_signals.signals
        negative = {signal.category: signal for signal in signals if signal.direction == SignalDirection.NEGATIVE}
        analysis_text = " ".join(
            statement.text.lower()
            for section in (
                request.financial_analysis_result.financial_trend,
                request.financial_analysis_result.profitability_analysis,
                request.financial_analysis_result.risks,
            )
            for statement in section
        )
        leverage = negative.get(SignalCategory.LEVERAGE)
        if leverage or any(token in analysis_text for token in ("nợ tăng nhanh", "no tang nhanh", "debt growth", "liabilities tăng")):
            refs = leverage.evidence_refs if leverage else self._refs(request.financial_analysis_result.risks)
            if refs:
                risks.append(self._risk(RiskType.LEVERAGE, RiskSeverity.HIGH, "NEGATIVE", "Có evidence cho thấy áp lực đòn bẩy cần được xem xét.", refs, leverage.strength if leverage else "MEDIUM"))
            else:
                unknown.append("Leverage risk cannot be assessed because supporting evidence is missing.")

        profit_positive = any(signal.category == SignalCategory.PROFITABILITY and signal.direction == SignalDirection.POSITIVE for signal in signals)
        cashflow_negative = any(signal.category == SignalCategory.CASHFLOW and signal.direction == SignalDirection.NEGATIVE for signal in signals)
        if profit_positive and cashflow_negative:
            refs = self._signal_refs(signals, {SignalCategory.PROFITABILITY, SignalCategory.CASHFLOW})
            if refs:
                risks.append(self._risk(RiskType.EARNINGS_QUALITY, RiskSeverity.MEDIUM, "NEGATIVE", "Lợi nhuận tăng nhưng dòng tiền giảm theo các signal hiện có.", refs, "MEDIUM"))
            else:
                unknown.append("Earnings quality cannot be assessed without evidence references.")

        growth = negative.get(SignalCategory.GROWTH)
        if growth:
            risks.append(self._risk(RiskType.GROWTH, RiskSeverity.MEDIUM, "NEGATIVE", "Evidence cho thấy tín hiệu tăng trưởng suy yếu hoặc chậm lại.", growth.evidence_refs, growth.strength))

        for benchmark in request.benchmark_result.benchmarks:
            if benchmark.benchmark_type.value == "INDUSTRY" and benchmark.position == Position.BELOW:
                if benchmark.evidence_refs:
                    risks.append(self._risk(RiskType.FINANCIAL, RiskSeverity.MEDIUM, "NEGATIVE", "Doanh nghiệp thấp hơn benchmark ngành theo evidence.", benchmark.evidence_refs, benchmark.confidence))
                else:
                    unknown.append(f"Relative weakness for {benchmark.metric} lacks evidence references.")

        if request.benchmark_result.limitations:
            unknown.extend(request.benchmark_result.limitations)
        if not risks and not unknown:
            unknown.append("Chưa có evidence rủi ro đủ rõ để đánh giá.")
        level = self._overall_level(risks, unknown)
        confidence = min(request.financial_analysis_result.confidence_score, request.financial_signals.confidence, 100)
        if unknown:
            confidence = min(confidence, 69)
        return RiskReviewResult(
            overall_risk_level=level, risks=risks,
            risk_summary="Có rủi ro được nhận diện từ evidence." if risks else "Chưa đủ evidence để xác định mức rủi ro tổng thể.",
            unknown_risks=list(dict.fromkeys(unknown)), confidence=confidence,
        )

    @staticmethod
    def _risk(risk_type: RiskType, severity: RiskSeverity, direction: str, statement: str, refs: list[str], confidence: str) -> RiskItem:
        return RiskItem(type=risk_type, severity=severity, direction=direction, statement=statement, evidence_refs=list(dict.fromkeys(refs)), confidence=confidence)

    @staticmethod
    def _refs(statements: list[Any]) -> list[str]:
        return [ref for statement in statements for ref in statement.evidence_refs]

    @staticmethod
    def _signal_refs(signals: list[Any], categories: set[SignalCategory]) -> list[str]:
        return [ref for signal in signals if signal.category in categories for ref in signal.evidence_refs]

    @staticmethod
    def _overall_level(risks: list[RiskItem], unknown: list[str]) -> RiskSeverity:
        if any(risk.severity == RiskSeverity.HIGH for risk in risks):
            return RiskSeverity.HIGH
        if risks:
            return RiskSeverity.MEDIUM
        return RiskSeverity.UNKNOWN
