"""Financial Question Understanding skill.

This module only turns a user question into a validated blueprint.  It is
deliberately side-effect free: it never queries a database, vector store or
web search and it never produces financial values.
"""
from __future__ import annotations

import json
import re
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.services.intent_router import (
    normalize_text,
    resolve_metrics,
    resolve_sector,
    resolve_tickers,
    resolve_years,
)
from src.services.query_tools import ticker_taxonomy


class Intent(StrEnum):
    FACT_LOOKUP = "FACT_LOOKUP"
    TIME_SERIES_ANALYSIS = "TIME_SERIES_ANALYSIS"
    COMPANY_COMPARISON = "COMPANY_COMPARISON"
    COMPANY_EVALUATION = "COMPANY_EVALUATION"
    FINANCIAL_HEALTH_ANALYSIS = "FINANCIAL_HEALTH_ANALYSIS"
    INVESTMENT_RESEARCH = "INVESTMENT_RESEARCH"
    RISK_ANALYSIS = "RISK_ANALYSIS"
    TREND_ANALYSIS = "TREND_ANALYSIS"


AnalysisType = Literal[
    "growth", "profitability", "efficiency", "leverage", "cashflow",
    "valuation", "business_quality", "industry_context",
]
EvidenceType = Literal["NUMERIC", "DERIVED_METRIC", "QUALITATIVE", "EXTERNAL"]
EvidenceName = Literal[
    "revenue", "revenue_growth", "profit", "profit_growth", "net_margin",
    "total_assets", "total_liabilities", "total_equity", "roa", "roe",
    "cash_flow", "valuation_multiple", "business_driver", "company_profile",
    "management", "industry_context", "current_events",
]


class BlueprintPeriod(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: str = ""
    end: str = ""

    @field_validator("start", "end")
    @classmethod
    def valid_year_or_empty(cls, value: str) -> str:
        if value and not re.fullmatch(r"(?:19|20)\d{2}", value):
            raise ValueError("period must be an empty string or a four-digit year")
        return value


class EvidenceRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: EvidenceName
    type: EvidenceType


class FinancialAnalysisBlueprint(BaseModel):
    """Strict, answer-free contract consumed by the planning layer."""

    model_config = ConfigDict(extra="forbid")
    intent: Intent
    companies: list[str] = Field(default_factory=list)
    sector: list[str] = Field(default_factory=list)
    period: BlueprintPeriod = Field(default_factory=BlueprintPeriod)
    analysis_type: list[AnalysisType] = Field(default_factory=list)
    required_evidence: list[EvidenceRequirement] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)

    @field_validator("companies")
    @classmethod
    def normalized_companies(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip().upper() for value in values if value.strip()))

    @field_validator("sector")
    @classmethod
    def normalized_sector(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip().upper() for value in values if value.strip()))


class FinancialQuestionUnderstandingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_query: str = Field(min_length=1, max_length=2000)


class FinancialQuestionUnderstandingSkill:
    """Rule-grounded understanding with an optional validated LLM refinement."""

    def __init__(self, llm_client: Any | None = None) -> None:
        self.llm_client = llm_client
        self.last_failure: str | None = None
        self.last_used_llm = False

    def understand(self, user_query: str) -> FinancialAnalysisBlueprint:
        request = FinancialQuestionUnderstandingInput(user_query=user_query)
        self.last_failure = None
        self.last_used_llm = False
        deterministic = self._deterministic(request.user_query)
        if self.llm_client is None:
            return deterministic
        try:
            raw = self.llm_client.generate(self._system_prompt(), request.user_query)
            candidate = FinancialAnalysisBlueprint.model_validate(json.loads(raw))
            self._ground_candidate(candidate, deterministic)
            self.last_used_llm = True
            return candidate
        except (Exception) as exc:  # provider and validation failures are safe fallbacks
            self.last_failure = f"QUESTION_UNDERSTANDING_LLM_FAILURE: {type(exc).__name__}"
            return deterministic

    def _system_prompt(self) -> str:
        return (
            "You are a financial question understanding component. Return JSON only "
            "matching FinancialAnalysisBlueprint. Do not answer the question, call tools, "
            "invent numbers, companies, metrics, dates, or fields. Use only the declared "
            "intent, analysis_type, evidence names and evidence types. Empty values are "
            "preferred when the question does not provide them."
        )

    def _ground_candidate(
        self, candidate: FinancialAnalysisBlueprint, deterministic: FinancialAnalysisBlueprint,
    ) -> None:
        allowed_companies = set(deterministic.companies)
        if not set(candidate.companies).issubset(allowed_companies):
            raise ValueError("LLM introduced an unresolved company")
        if candidate.period != deterministic.period and (
            deterministic.period.start or deterministic.period.end
        ):
            raise ValueError("LLM changed an explicit period")
        if deterministic.sector and not set(candidate.sector).issubset(set(deterministic.sector)):
            raise ValueError("LLM introduced an unresolved sector")

    def _deterministic(self, question: str) -> FinancialAnalysisBlueprint:
        text = normalize_text(question)
        tickers, _ = resolve_tickers(question)
        metrics = resolve_metrics(question)
        resolved_sector = resolve_sector(question)
        if resolved_sector is None and tickers:
            resolved_sector = ticker_taxonomy().get(tickers[0])
        time = resolve_years(question)
        years = [str(year) for year in time.get("years", [])]
        period = BlueprintPeriod(start=years[0] if years else "", end=years[-1] if years else "")

        has_rank = any(cue in text for cue in ("xep hang", "top ", "cao nhat", "thap nhat"))
        has_compare = any(cue in text for cue in ("so sanh", "doi chieu", "so voi"))
        has_health = any(cue in text for cue in ("suc khoe tai chinh", "khoe len", "yeu di"))
        has_investment = any(cue in text for cue in ("dau tu", "trien vong", "co nen mua"))
        has_risk = any(cue in text for cue in ("rui ro", "nguy co", "anh huong", "su kien gan day"))
        has_trend = any(cue in text for cue in ("tang truong", "xu huong", "tang hay giam"))
        has_evaluation = any(cue in text for cue in ("danh gia", "phan tich co phieu", "phan tich ma"))
        is_range = time.get("is_range") or len(years) > 1 or "nam gan nhat" in text

        if has_health:
            intent = Intent.FINANCIAL_HEALTH_ANALYSIS
        elif has_investment:
            intent = Intent.INVESTMENT_RESEARCH
        elif has_risk:
            intent = Intent.RISK_ANALYSIS
        elif has_rank or has_compare or len(tickers) > 1:
            intent = Intent.COMPANY_COMPARISON
        elif has_trend or is_range:
            intent = Intent.TREND_ANALYSIS if has_trend else Intent.TIME_SERIES_ANALYSIS
        elif has_evaluation:
            intent = Intent.COMPANY_EVALUATION
        else:
            intent = Intent.FACT_LOOKUP

        analysis: list[str] = []
        if has_trend or is_range or has_health or any(metric.endswith("growth") for metric in metrics):
            analysis.append("growth")
        if any(metric in metrics for metric in ("net_profit", "net_profit_margin", "roa", "roe")) or has_health:
            analysis.append("profitability")
        if any(cue in text for cue in ("hieu qua", "roa", "roe", "bien loi nhuan")) or has_health:
            analysis.append("efficiency")
        if any(cue in text for cue in ("don bay", "tong no", "no phai tra", "no vay")):
            analysis.append("leverage")
        if any(cue in text for cue in ("dong tien", "luu chuyen tien")):
            analysis.append("cashflow")
        if any(cue in text for cue in ("dinh gia", "p/e", "p/b", "gia muc tieu")):
            analysis.append("valuation")
        if any(cue in text for cue in ("nganh", "thi truong", "boi canh")):
            analysis.append("industry_context")
        if has_evaluation and not analysis:
            analysis.append("business_quality")
        analysis = list(dict.fromkeys(analysis))

        evidence: list[EvidenceRequirement] = []
        def add(name: EvidenceName, kind: EvidenceType) -> None:
            if not any(item.name == name for item in evidence):
                evidence.append(EvidenceRequirement(name=name, type=kind))
        if "growth" in analysis:
            add("revenue_growth", "DERIVED_METRIC")
            add("profit_growth", "DERIVED_METRIC")
        if "profitability" in analysis:
            add("profit", "NUMERIC")
            add("net_margin", "DERIVED_METRIC")
        if "efficiency" in analysis:
            add("roa", "DERIVED_METRIC")
            add("roe", "DERIVED_METRIC")
        if "leverage" in analysis:
            add("total_liabilities", "NUMERIC")
            add("total_assets", "NUMERIC")
        if "cashflow" in analysis:
            add("cash_flow", "NUMERIC")
        if "valuation" in analysis:
            add("valuation_multiple", "NUMERIC")
        if "industry_context" in analysis:
            add("industry_context", "QUALITATIVE")
        if has_health:
            add("business_driver", "QUALITATIVE")
        if has_risk:
            add("current_events", "EXTERNAL")
        metric_evidence: dict[str, tuple[EvidenceName, EvidenceType]] = {
            "net_revenue": ("revenue", "NUMERIC"),
            "net_profit": ("profit", "NUMERIC"),
            "total_assets": ("total_assets", "NUMERIC"),
            "total_liabilities": ("total_liabilities", "NUMERIC"),
            "total_equity": ("total_equity", "NUMERIC"),
            "roa": ("roa", "DERIVED_METRIC"),
            "roe": ("roe", "DERIVED_METRIC"),
            "net_profit_margin": ("net_margin", "DERIVED_METRIC"),
            "net_revenue_yoy_growth": ("revenue_growth", "DERIVED_METRIC"),
            "net_profit_yoy_growth": ("profit_growth", "DERIVED_METRIC"),
        }
        for metric in metrics:
            mapped = metric_evidence.get(metric)
            if mapped:
                add(*mapped)
        if not evidence and any(cue in text for cue in ("kinh doanh gi", "nganh nghe", "thong tin doanh nghiep")):
            add("company_profile", "QUALITATIVE")
        if any(cue in text for cue in ("ban lanh dao", "lanh dao", "tong giam doc", "chu tich")):
            add("management", "QUALITATIVE")

        risks: list[str] = []
        if not tickers and not resolved_sector:
            risks.append("MISSING_COMPANY_OR_SECTOR")
        if not period.start:
            risks.append("PERIOD_UNSPECIFIED")
        if "nam gan nhat" in text:
            risks.append("LATEST_PERIOD_REQUIRES_DATA_RESOLUTION")
        if has_rank and not tickers:
            risks.append("COMPANY_RESOLVED_FROM_RANK_RESULT")
        if "cashflow" in analysis or "valuation" in analysis:
            risks.append("EVIDENCE_MAY_REQUIRE_ADDITIONAL_DATA_SOURCE")
        return FinancialAnalysisBlueprint(
            intent=intent, companies=tickers,
            sector=[resolved_sector] if resolved_sector else [], period=period,
            analysis_type=analysis, required_evidence=evidence, risk_flags=risks,
        )
