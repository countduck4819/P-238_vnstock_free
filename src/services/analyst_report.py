"""Traceable analyst report generation from structured analysis objects."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.services.benchmark_engine import BenchmarkResult
from src.services.financial_interpretation import FinancialSignalResult
from src.services.financial_reasoning import FinancialAnalysisResult
from src.services.risk_review import RiskReviewResult


class AnalystReportInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    financial_analysis_result: FinancialAnalysisResult
    financial_signals: FinancialSignalResult
    benchmark_result: BenchmarkResult
    risk_review: RiskReviewResult


class AnalystReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    executive_summary: str
    financial_assessment: str
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    benchmark_summary: str
    unknowns: list[str] = Field(default_factory=list)
    confidence: str
    evidence_coverage: str


class AnalystReportGenerator:
    """Render only supplied analysis objects; no external calls are made."""

    def generate(self, payload: AnalystReportInput | dict[str, Any]) -> AnalystReport:
        data = payload if isinstance(payload, AnalystReportInput) else AnalystReportInput.model_validate(payload)
        company = data.benchmark_result.company
        strengths = self._statements(data.financial_analysis_result.strengths, "FACT")
        strengths.extend(self._signals(data.financial_signals, "POSITIVE"))
        weaknesses = self._signals(data.financial_signals, "NEGATIVE")
        if not weaknesses:
            weaknesses = [self._statement(item) for item in data.financial_analysis_result.unknowns[:3]]
        risks = [self._risk(item) for item in data.risk_review.risks]
        if not risks and data.risk_review.overall_risk_level.value == "UNKNOWN":
            risks.append("UNKNOWN: Chưa có risk evidence đủ rõ để đánh giá.")
        unknowns = [self._statement(item) for item in data.financial_analysis_result.unknowns]
        unknowns.extend(f"UNKNOWN: {item}" for item in data.risk_review.unknown_risks)
        unknowns.extend(f"UNKNOWN: {item}" for item in data.benchmark_result.limitations)
        unknowns = list(dict.fromkeys(unknowns))
        assessment = self._assessment(data.financial_analysis_result, data.financial_signals)
        benchmark = self._benchmark(data.benchmark_result)
        score = min(
            data.financial_analysis_result.confidence_score,
            data.financial_signals.confidence,
            data.risk_review.confidence,
        )
        confidence = "HIGH" if score >= 80 else "MEDIUM" if score >= 70 else "LOW"
        coverage = self._coverage(data, unknowns)
        return AnalystReport(
            title=f"Analyst Report - {company}",
            executive_summary=self._summary(data, company),
            financial_assessment=assessment,
            strengths=strengths or ["UNKNOWN: Chưa xác định được điểm mạnh từ input."],
            weaknesses=weaknesses or ["UNKNOWN: Chưa xác định được điểm yếu từ input."],
            risks=risks,
            benchmark_summary=benchmark,
            unknowns=unknowns or ["UNKNOWN: Không có hạn chế bổ sung được cung cấp."],
            confidence=confidence,
            evidence_coverage=coverage,
        )

    @staticmethod
    def _statement(statement: Any) -> str:
        refs = ", ".join(statement.evidence_refs) if statement.evidence_refs else "none"
        return f"{statement.type.value}: {statement.text} [Evidence: {refs}]"

    @classmethod
    def _statements(cls, statements: list[Any], kind: str) -> list[str]:
        return [f"{kind}: {item.text} [Evidence: {', '.join(item.evidence_refs) or 'none'}]" for item in statements]

    @classmethod
    def _signals(cls, result: FinancialSignalResult, direction: str) -> list[str]:
        return [
            f"INTERPRETATION: {signal.explanation} [Evidence: {', '.join(signal.evidence_refs) or 'none'}]"
            for signal in result.signals if signal.direction.value == direction
        ]

    @staticmethod
    def _risk(item: Any) -> str:
        return f"RISK: {item.statement} [Evidence: {', '.join(item.evidence_refs)}]"

    @classmethod
    def _summary(cls, data: AnalystReportInput, company: str) -> str:
        pieces = [f"FACT: Báo cáo {company} chỉ sử dụng các analysis objects đã cung cấp."]
        if data.risk_review.risks:
            pieces.append(f"RISK: Ghi nhận {len(data.risk_review.risks)} nhóm rủi ro trong risk review.")
        if data.benchmark_result.benchmarks:
            pieces.append("INTERPRETATION: Có benchmark được cung cấp để đánh giá tương đối.")
        if data.risk_review.unknown_risks:
            pieces.append("UNKNOWN: Một số rủi ro chưa thể kết luận do thiếu evidence.")
        return " ".join(pieces)

    @classmethod
    def _assessment(cls, analysis: FinancialAnalysisResult, signals: FinancialSignalResult) -> str:
        sections = [cls._statements(analysis.financial_trend, "FACT"), cls._statements(analysis.profitability_analysis, "FACT")]
        sections.append(cls._signals(signals, "POSITIVE"))
        return " ".join(item for section in sections for item in section) or "UNKNOWN: Chưa có financial assessment đủ căn cứ."

    @staticmethod
    def _benchmark(result: BenchmarkResult) -> str:
        if not result.benchmarks:
            return "UNKNOWN: Chưa có benchmark để so sánh."
        return " ".join(
            f"FACT: {item.metric} position {item.position.value} vs {item.benchmark_type.value} benchmark [Evidence: {', '.join(item.evidence_refs) or 'none'}]."
            for item in result.benchmarks
        )

    @staticmethod
    def _coverage(data: AnalystReportInput, unknowns: list[str]) -> str:
        if not unknowns:
            return "COMPLETE"
        if data.financial_analysis_result.confidence_score >= 70:
            return "PARTIAL"
        return "LIMITED"

