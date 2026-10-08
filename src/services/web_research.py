"""Controlled external research abstraction with deterministic source policy."""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, urlopen

from src.services.intent_router import normalize_text


class WebSearchClient(Protocol):
    def search(self, query: str, max_results: int) -> list[dict[str, Any]]: ...


class TavilyWebSearchClient:
    """Provider adapter kept outside the LangGraph nodes."""

    endpoint = "https://api.tavily.com/search"

    def __init__(self, api_key: str, timeout_seconds: float = 15.0) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, max_results: int) -> list[dict[str, Any]]:
        payload = json.dumps({
            "api_key": self.api_key, "query": query,
            "max_results": max_results, "search_depth": "advanced",
            "include_answer": False, "include_raw_content": False,
        }).encode("utf-8")
        request = Request(
            self.endpoint, data=payload,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
            body = json.loads(response.read().decode("utf-8"))
        return list(body.get("results") or [])


TIER_1_MARKERS = (
    ".gov.", "gov.vn", "hsx.vn", "hnx.vn", "ssc.gov.vn", "investor",
    "ir.", "congbothongtin",
)
TIER_2_DOMAINS = {
    "reuters.com", "bloomberg.com", "vneconomy.vn", "cafef.vn",
    "vietnamfinance.vn", "baodautu.vn", "theinvestor.vn",
}
DEFAULT_OFFICIAL_DOMAINS = {
    "fpt.com", "fpt.com.vn", "mbbank.com.vn", "vietcombank.com.vn",
    "bidv.com.vn", "vietinbank.vn", "techcombank.com",
    "hsx.vn", "hnx.vn", "ssc.gov.vn",
}
REJECTED_DOMAINS = {
    "facebook.com", "tiktok.com", "youtube.com", "blogspot.com",
    "wordpress.com", "reddit.com",
}


def _canonical_url(value: str) -> str:
    parsed = urlparse(value)
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, "", "", ""))


def _parse_date(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


class WebSourcePolicy:
    def __init__(
        self, *, max_sources: int = 10, max_total_content: int = 12_000,
        official_domains: set[str] | None = None,
    ) -> None:
        self.max_sources = min(max(1, max_sources), 10)
        self.max_total_content = min(max(1000, max_total_content), 30_000)
        configured = {
            value.strip().lower()
            for value in os.environ.get("WEB_OFFICIAL_DOMAINS", "").split(",")
            if value.strip()
        }
        self.official_domains = set(official_domains or DEFAULT_OFFICIAL_DOMAINS) | configured

    def curate(
        self, query: str, raw_results: list[dict[str, Any]], *, recency_days: int | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        accepted: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        seen: set[str] = set()
        consumed = 0
        query_tokens = set(normalize_text(query).split())
        now = datetime.now(UTC)
        for index, raw in enumerate(raw_results):
            url = str(raw.get("url") or "").strip()
            title = str(raw.get("title") or "").strip()
            summary = str(raw.get("summary") or raw.get("content") or raw.get("snippet") or "").strip()
            domain = urlparse(url).netloc.lower().removeprefix("www.")
            canonical = _canonical_url(url)
            reason = None
            if not url.startswith(("http://", "https://")) or not title or not summary:
                reason = "INCOMPLETE_SOURCE"
            elif domain in REJECTED_DOMAINS or any(domain.endswith(f".{item}") for item in REJECTED_DOMAINS):
                reason = "LOW_TRUST_DOMAIN"
            elif canonical in seen:
                reason = "DUPLICATE_SOURCE"
            else:
                source_tokens = set(normalize_text(f"{title} {summary}").split())
                significant = {token for token in query_tokens if len(token) >= 3}
                if significant and not significant.intersection(source_tokens):
                    reason = "IRRELEVANT_SOURCE"
            published = _parse_date(raw.get("published_date") or raw.get("date"))
            if reason is None and recency_days and published:
                if published < now - timedelta(days=max(1, recency_days)):
                    reason = "STALE_SOURCE"
            if reason:
                rejected.append({"title": title[:200], "url": url[:500], "reason": reason})
                continue
            seen.add(canonical)
            source_category, reliability = self._classify(domain, raw)
            remaining = self.max_total_content - consumed
            if remaining <= 0 or len(accepted) >= self.max_sources:
                rejected.append({"title": title[:200], "url": url[:500], "reason": "WEB_BUDGET_REACHED"})
                continue
            compact_summary = summary[: min(2000, remaining)]
            consumed += len(compact_summary)
            accepted.append({
                "source_id": f"web-{len(accepted)}",
                "title": title[:300], "publisher": raw.get("publisher") or domain,
                "domain": domain, "url": url,
                "publication_date": published.isoformat() if published else None,
                "retrieval_time": now.isoformat(), "summary": compact_summary,
                "source_category": source_category, "reliability": reliability,
                "confidence": raw.get("score"),
                "claim_key": raw.get("claim_key"), "claim_value": raw.get("claim_value"),
            })
        return accepted, rejected, self._conflicts(accepted)

    def _classify(self, domain: str, raw: dict[str, Any]) -> tuple[str, str]:
        supplied = str(raw.get("source_category") or "").lower()
        official_domain = any(
            domain == value or domain.endswith(f".{value}")
            for value in self.official_domains
        )
        if supplied == "official" or official_domain or any(marker in domain for marker in TIER_1_MARKERS):
            return "official", "TIER_1"
        if supplied == "news" or domain in TIER_2_DOMAINS:
            return "news", "TIER_2"
        return "other", "TIER_3"

    @staticmethod
    def _conflicts(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, list[str]]] = {}
        for source in sources:
            key = source.get("claim_key")
            value = source.get("claim_value")
            if key and value is not None:
                grouped.setdefault(str(key), {}).setdefault(str(value), []).append(source["source_id"])
        return [
            {"claim_key": key, "values": values, "preferred": _preferred_source(values, sources)}
            for key, values in grouped.items() if len(values) > 1
        ]


def _preferred_source(values: dict[str, list[str]], sources: list[dict[str, Any]]) -> str | None:
    by_id = {source["source_id"]: source for source in sources}
    ranked = sorted(
        (source_id for ids in values.values() for source_id in ids),
        key=lambda source_id: by_id[source_id].get("reliability", "TIER_9"),
    )
    return ranked[0] if ranked else None


class ControlledWebResearch:
    def __init__(self, client: WebSearchClient, policy: WebSourcePolicy | None = None) -> None:
        self.client = client
        self.policy = policy or WebSourcePolicy()

    def search(
        self, query: str, *, max_results: int = 5, recency_days: int | None = 365,
    ) -> dict[str, Any]:
        try:
            raw = self.client.search(query, min(max(1, max_results), 10))
            sources, rejected, conflicts = self.policy.curate(
                query, raw, recency_days=recency_days,
            )
            return {
                "tool": "web_search", "status": "OK" if sources else "NO_RESULTS",
                "query": query, "data": sources, "web_sources": sources,
                "rejected_sources": rejected, "source_conflicts": conflicts,
                "source": "WEB", "warnings": [], "errors": [],
            }
        except Exception as exc:
            return {
                "tool": "web_search", "status": "TOOL_UNAVAILABLE", "query": query,
                "data": [], "web_sources": [], "rejected_sources": [],
                "source_conflicts": [], "source": "WEB", "warnings": [],
                "errors": [{"code": "WEB_SEARCH_UNAVAILABLE", "message": type(exc).__name__}],
            }


def build_default_web_research() -> ControlledWebResearch | None:
    if os.environ.get("FINSIGHT_ENABLE_WEB", "false").strip().lower() != "true":
        return None
    provider = os.environ.get("WEB_SEARCH_PROVIDER", "tavily").strip().lower()
    if provider != "tavily":
        return None
    api_key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not api_key:
        return None
    return ControlledWebResearch(TavilyWebSearchClient(api_key))
