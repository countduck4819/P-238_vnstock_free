"""Deterministic interpretation of an evidence-bounded financial analysis."""
from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.services.financial_reasoning import FinancialAnalysisResult, ReasoningStatement


class SignalCategory(StrEnum):
    GROWTH = "GROWTH"
    PROFITABILITY = "PROFITABILITY"
    EFFICIENCY = "EFFICIENCY"
    LEVERAGE = "LEVERAGE"
    CASHFLOW = "CASHFLOW"
    BUSINESS_QUALITY = "BUSINESS_QUALITY"


class SignalDirection(StrEnum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"
    UNKNOWN = "UNKNOWN"


class FinancialSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    category: SignalCategory
    direction: SignalDirection
    strength: Literal["HIGH", "MEDIUM", "LOW"]
    explanation: str = Field(min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def grounded_signal(self) -> FinancialSignal:
        if self.direction != SignalDirection.UNKNOWN and not self.evidence_refs:
            raise ValueError("Non-unknown signals require evidence references")
        return self


class FinancialSignalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    signals: list[FinancialSignal] = Field(default_factory=list)
    overall_assessment: str
    investment_relevance: str
    confidence: int = Field(ge=0, le=100)


class FinancialInterpretationEngine:
    """Translate only existing FACT/INFERENCE statements into signals."""

    def interpret(self, result: FinancialAnalysisResult | dict[str, Any]) -> FinancialSignalResult:
        analysis = result if isinstance(result, FinancialAnalysisResult) else FinancialAnalysisResult.model_validate(result)
        statements = self._statements(analysis)
        signals: list[FinancialSignal] = []
        self._growth_signal(statements, signals)
        self._profitability_signal(statements, signals)
        self._efficiency_signal(statements, signals)
        self._leverage_signal(statements, signals)
        self._cashflow_signal(statements, signals)
        self._business_signal(statements, signals)
        if not signals:
            signals.append(FinancialSignal(
                name="insufficient_evidence", category=SignalCategory.BUSINESS_QUALITY,
                direction=SignalDirection.UNKNOWN, strength="LOW",
                explanation="Chưa có FACT hoặc INFERENCE đủ căn cứ để tạo financial signal.",
            ))
        known = [signal for signal in signals if signal.direction != SignalDirection.UNKNOWN]
        if known:
            overall = "Các financial signal được tạo từ evidence đã cung cấp; không bổ sung dữ liệu ngoài package."
        else:
            overall = "Chưa đủ evidence để xác định hướng tín hiệu tài chính."
        relevance = "Các signal chỉ hỗ trợ nghiên cứu và cần được xem cùng độ tin cậy, hạn chế và nguồn evidence; không phải quyết định giao dịch."
        return FinancialSignalResult(
            signals=signals, overall_assessment=overall,
            investment_relevance=relevance, confidence=analysis.confidence_score,
        )

    @staticmethod
    def _statements(analysis: FinancialAnalysisResult) -> list[ReasoningStatement]:
        sections = (
            analysis.executive_summary, analysis.financial_trend,
            analysis.profitability_analysis, analysis.business_quality,
            analysis.strengths, analysis.risks, analysis.unknowns,
        )
        return [statement for section in sections for statement in section]

    @staticmethod
    def _add(
        signals: list[FinancialSignal], name: str, category: SignalCategory,
        direction: SignalDirection, strength: Literal["HIGH", "MEDIUM", "LOW"],
        explanation: str, statements: list[ReasoningStatement],
    ) -> None:
        refs = list(dict.fromkeys(ref for statement in statements for ref in statement.evidence_refs))
        signals.append(FinancialSignal(
            name=name, category=category, direction=direction,
            strength=strength, explanation=explanation, evidence_refs=refs,
        ))

    def _growth_signal(self, statements: list[ReasoningStatement], signals: list[FinancialSignal]) -> None:
        growth = [item for item in statements if any(token in item.text.lower() for token in ("tăng trưởng", "growth"))]
        if not growth:
            return
        text = " ".join(item.text.lower() for item in growth)
        if "chất lượng tăng trưởng" in text and "cải thiện" in text:
            self._add(signals, "quality_growth", SignalCategory.GROWTH, SignalDirection.POSITIVE, "HIGH", "Profit growth and profitability improvement are supported by the reasoning evidence.", growth)
        elif "chưa chuyển hóa" in text or "concern" in text:
            self._add(signals, "quality_growth_concern", SignalCategory.GROWTH, SignalDirection.NEGATIVE, "MEDIUM", "Revenue growth is not shown to have converted into profit growth by the available evidence.", growth)
        else:
            self._add(signals, "growth_signal", SignalCategory.GROWTH, SignalDirection.UNKNOWN, "LOW", "Có evidence về tăng trưởng nhưng chưa đủ để xác định hướng chất lượng tăng trưởng.", growth)

    def _profitability_signal(self, statements: list[ReasoningStatement], signals: list[FinancialSignal]) -> None:
        matches = [item for item in statements if any(token in item.text.lower() for token in ("sinh lời", "profitability", "margin", "roa", "roe"))]
        if matches:
            self._add(signals, "profitability_signal", SignalCategory.PROFITABILITY, SignalDirection.UNKNOWN, "MEDIUM", "Đã có evidence về khả năng sinh lời; hướng cải thiện hay suy giảm chưa được xác nhận đầy đủ.", matches)

    def _efficiency_signal(self, statements: list[ReasoningStatement], signals: list[FinancialSignal]) -> None:
        matches = [item for item in statements if any(token in item.text.lower() for token in ("hiệu quả", "efficiency", "roa", "roe"))]
        if matches:
            self._add(signals, "efficiency_signal", SignalCategory.EFFICIENCY, SignalDirection.UNKNOWN, "MEDIUM", "Evidence hiệu quả được ghi nhận nhưng chưa đủ căn cứ để kết luận hướng tín hiệu.", matches)

    def _leverage_signal(self, statements: list[ReasoningStatement], signals: list[FinancialSignal]) -> None:
        matches = [item for item in statements if any(token in item.text.lower() for token in ("đòn bẩy", "leverage", "nợ", "liabilities"))]
        if matches:
            self._add(signals, "leverage_signal", SignalCategory.LEVERAGE, SignalDirection.UNKNOWN, "MEDIUM", "Có evidence liên quan đến đòn bẩy hoặc nợ nhưng chưa đủ để xác định rủi ro.", matches)

    def _cashflow_signal(self, statements: list[ReasoningStatement], signals: list[FinancialSignal]) -> None:
        matches = [item for item in statements if any(token in item.text.lower() for token in ("cashflow", "dòng tiền", "luân chuyển tiền"))]
        if matches:
            self._add(signals, "cashflow_signal", SignalCategory.CASHFLOW, SignalDirection.UNKNOWN, "LOW", "Evidence dòng tiền hiện có chưa đủ để xác định hướng tín hiệu.", matches)

    def _business_signal(self, statements: list[ReasoningStatement], signals: list[FinancialSignal]) -> None:
        matches = [item for item in statements if item.type.value == "FACT" and any(token in item.text.lower() for token in ("công nghệ", "kinh doanh", "business", "lợi thế"))]
        if matches:
            self._add(signals, "business_quality_signal", SignalCategory.BUSINESS_QUALITY, SignalDirection.UNKNOWN, "LOW", "Evidence định tính mô tả hoạt động kinh doanh nhưng chưa đủ để kết luận lợi thế cạnh tranh.", matches)
