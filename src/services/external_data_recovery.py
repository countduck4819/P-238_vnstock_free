"""External financial data recovery with ranked, provenance-rich evidence.

This component returns evidence only. It never writes PostgreSQL and never
promotes an external value to numerical truth.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from src.services.web_research import DEFAULT_OFFICIAL_DOMAINS, TIER_1_MARKERS, TIER_2_DOMAINS

logger = logging.getLogger(__name__)


class ExternalSearchClient(Protocol):
    def search(self, query: str, max_results: int) -> list[dict[str, Any]]: ...


class MissingEvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric: str = Field(min_length=1, max_length=100)
    year: int | None = Field(default=None, ge=1900, le=2100)


class RecoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company: str = Field(min_length=1, max_length=20)
    missing: list[MissingEvidenceItem] = Field(min_length=1, max_length=50)


class ExternalEvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric: str
    value: str
    source: str
    source_type: str
    confidence: str
    retrieved_date: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RecoveryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence: list[ExternalEvidenceItem] = Field(default_factory=list)


@dataclass(frozen=True)
class RankedSource:
    tier: int
    source_type: str
    confidence: str


class ExternalSourceRegistry:
    """Classify and rank sources without trusting arbitrary text as a value."""

    def rank(self, raw: dict[str, Any]) -> RankedSource | None:
        url = str(raw.get("url") or "").strip()
        title = str(raw.get("title") or "").strip().lower()
        publisher = str(raw.get("publisher") or "").strip()
        if not url.startswith(("https://", "http://")) or not title or not publisher:
            return None
        domain = urlparse(url).netloc.lower().removeprefix("www.")
        supplied = str(raw.get("source_type") or raw.get("source_category") or "").lower()
        tier1_title = any(
            token in title
            for token in ("annual report", "audited", "financial statement", "investor relations", "company announcement", "filing")
        )
        official = domain in DEFAULT_OFFICIAL_DOMAINS or any(
            domain == value or domain.endswith(f".{value}") for value in DEFAULT_OFFICIAL_DOMAINS
        )
        tier1 = official or tier1_title or supplied in {"official", "tier_1", "tier1"} or any(
            marker in domain for marker in TIER_1_MARKERS
        )
        if tier1:
            return RankedSource(1, "TIER_1", "HIGH")
        tier2 = supplied in {"reliable_database", "database", "tier_2", "tier2"} or domain in TIER_2_DOMAINS
        if tier2:
            return RankedSource(2, "TIER_2", "MEDIUM")
        return RankedSource(3, "TIER_3", "LOW")


class ExternalFinancialDataRecoveryAgent:
    """Recover explicitly missing evidence with bounded retries and timeout."""

    def __init__(
        self,
        client: ExternalSearchClient,
        *,
        max_retries: int = 2,
        timeout_seconds: float = 15.0,
        max_results: int = 10,
        source_registry: ExternalSourceRegistry | None = None,
    ) -> None:
        self.client = client
        self.max_retries = max(0, min(max_retries, 5))
        self.timeout_seconds = max(0.1, min(timeout_seconds, 120.0))
        self.max_results = max(1, min(max_results, 10))
        self.sources = source_registry or ExternalSourceRegistry()

    def recover(self, request: RecoveryRequest | dict[str, Any]) -> RecoveryResult:
        request = request if isinstance(request, RecoveryRequest) else RecoveryRequest.model_validate(request)
        recovered: list[ExternalEvidenceItem] = []
        for missing in request.missing:
            query = self._query(request.company, missing)
            raw_results, attempts = self._search_with_retry(query)
            candidates: list[tuple[RankedSource, dict[str, Any]]] = []
            for raw in raw_results:
                ranked = self.sources.rank(raw)
                value = raw.get("value", raw.get("claim_value"))
                if ranked is not None and value is not None and str(value).strip():
                    candidates.append((ranked, raw))
            candidates.sort(key=lambda item: item[0].tier)
            if not candidates:
                logger.warning("No identified external source for metric=%s company=%s", missing.metric, request.company)
                continue
            ranked, raw = candidates[0]
            retrieved = datetime.now(UTC).isoformat()
            url = str(raw["url"]).strip()
            recovered.append(ExternalEvidenceItem(
                metric=missing.metric, value=str(raw.get("value", raw.get("claim_value"))).strip(),
                source=url, source_type=ranked.source_type, confidence=ranked.confidence,
                retrieved_date=retrieved,
                metadata={
                    "company": request.company, "year": missing.year,
                    "title": str(raw.get("title"))[:300],
                    "publisher": str(raw.get("publisher"))[:200],
                    "domain": urlparse(url).netloc.lower().removeprefix("www."),
                    "published_date": raw.get("published_date") or raw.get("date"),
                    "query": query, "attempts": attempts,
                    "numerical_truth": False,
                },
            ))
        logger.info("External recovery completed: company=%s recovered=%d", request.company, len(recovered))
        return RecoveryResult(evidence=recovered)

    def _search_with_retry(self, query: str) -> tuple[list[dict[str, Any]], int]:
        for attempt in range(1, self.max_retries + 2):
            pool = ThreadPoolExecutor(max_workers=1)
            try:
                future = pool.submit(self.client.search, query, self.max_results)
                return list(future.result(timeout=self.timeout_seconds) or []), attempt
            except (FutureTimeout, Exception) as exc:
                logger.warning("External search attempt %d failed: %s", attempt, type(exc).__name__)
            finally:
                pool.shutdown(wait=False, cancel_futures=True)
        return [], self.max_retries + 1

    @staticmethod
    def _query(company: str, missing: MissingEvidenceItem) -> str:
        year = f" {missing.year}" if missing.year else ""
        return f"{company} {missing.metric}{year} annual report audited financial statement"
