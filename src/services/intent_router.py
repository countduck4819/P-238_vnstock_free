"""Rule-first Vietnamese Intent Router and Query Planner MVP.

This module only creates structured query plans. It never executes a query or
imports a database, vector store, financial provider, or LLM client.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from src.services.query_tools import ticker_taxonomy

INTENTS = {
    "FACT", "TIME_SERIES", "COMPARE", "RANK",
    "COMPANY_KNOWLEDGE", "HYBRID", "EVALUATION", "MULTI_QUERY",
    "GREETING", "UNKNOWN",
}

# Explicit, reviewable MVP aliases. Matching is accent-insensitive but never fuzzy.
METRIC_ALIASES: dict[str, tuple[str, ...]] = {
    "net_profit": (
        "net_profit", "lợi nhuận sau thuế", "lợi nhuận ròng", "lãi ròng",
        "lnst", "lợi nhuận", "doanh thu sau thuế",
    ),
    "net_revenue": ("net_revenue", "doanh thu thuần", "doanh thu"),
    "profit_before_tax": ("profit_before_tax", "lợi nhuận trước thuế", "lntt"),
    "total_assets": ("total_assets", "tổng tài sản"),
    "total_liabilities": ("total_liabilities", "tổng nợ", "nợ phải trả"),
    "total_equity": ("total_equity", "vốn chủ sở hữu", "tổng vốn chủ sở hữu"),
    "net_interest_income": ("net_interest_income", "thu nhập lãi thuần"),
    "net_fee_and_commission_income": (
        "net_fee_and_commission_income", "thu nhập phí thuần",
        "thu nhập phí và hoa hồng thuần", "lãi thuần từ dịch vụ",
    ),
    "provision_for_credit_losses": (
        "provision_for_credit_losses", "dự phòng rủi ro tín dụng",
    ),
    "roa": ("roa", "tỷ suất sinh lời trên tài sản"),
    "roe": ("roe", "tỷ suất sinh lời trên vốn chủ sở hữu"),
    "net_profit_margin": ("net_profit_margin", "biên lợi nhuận ròng"),
    "net_profit_yoy_growth": (
        "net_profit_yoy_growth", "tăng trưởng lợi nhuận", "tăng trưởng lnst",
    ),
    "net_revenue_yoy_growth": (
        "net_revenue_yoy_growth", "tăng trưởng doanh thu",
    ),
}

SECTOR_ALIASES: dict[str, tuple[str, ...]] = {
    "CORPORATE": ("doanh nghiệp thường", "doanh nghiệp", "corporate"),
    "BANK": ("ngân hàng", "bank"),
    "SECURITIES": ("công ty chứng khoán", "chứng khoán", "securities"),
    "INSURANCE": ("bảo hiểm", "insurance"),
}

KNOWLEDGE_CUES: dict[str, tuple[str, ...]] = {
    "company_profile": (
        "kinh doanh gì", "làm gì", "mô hình kinh doanh", "ngành nghề",
        "lĩnh vực hoạt động", "hoạt động lĩnh vực gì",
        "hoạt động trong lĩnh vực nào", "hoạt động trong những lĩnh vực nào",
        "thông tin công ty", "thông tin doanh nghiệp",
    ),
    "company_history": ("lịch sử", "thành lập", "hình thành"),
    "management": (
        "ban lãnh đạo", "lãnh đạo", "chủ tịch", "tổng giám đốc", "những ai",
    ),
    "listing_info": ("niêm yết", "sàn giao dịch", "thông tin niêm yết"),
}

COMPARE_CUES = ("so sánh", "đối chiếu", "so với")
PERCENT_GROWTH_CUES = (
    "tang bao nhieu phan tram",
    "tang bao nhieu %",
    "tang bao nhieu phan-tram",
    "tang bao nhieu so voi",
)
YOY_GROWTH_BY_BASE_METRIC = {
    "net_revenue": "net_revenue_yoy_growth",
    "net_profit": "net_profit_yoy_growth",
}
YOY_GROWTH_METRICS = set(YOY_GROWTH_BY_BASE_METRIC.values())
RANK_CUES = (
    "top", "bottom", "rank", "highest", "lowest",
    "cao nhất", "lớn nhất", "thấp nhất", "nhỏ nhất", "xếp hạng",
)
LOW_DIRECTION_CUES = ("bottom", "lowest", "ascending", "thấp nhất", "nhỏ nhất")
HIGH_DIRECTION_CUES = ("highest", "descending", "cao nhất", "lớn nhất")
RANGE_CUES = ("giai đoạn", "từ", "đến", "qua các năm")
TREND_CUES = ("xu hướng", "giai đoạn", "qua các năm")
EVALUATION_CUES = (
    "đánh giá cổ phiếu", "đánh giá mã", "đánh giá doanh nghiệp",
    "phân tích cổ phiếu", "phân tích mã", "sức khỏe tài chính",
)
GENERIC_STOCK_CUES = (
    "cổ phiếu", "mã cổ phiếu", "thông tin về cổ phiếu",
    "hỏi về cổ phiếu", "tổng quan cổ phiếu",
)
TICKER_TOKEN_EXCLUSIONS = {
    "LNST", "LNTT", "ROA", "ROE", "TOP", "BOTTOM", "RANK",
    "HIGHEST", "LOWEST", "BANK", "CORPORATE",
    "SECURITIES", "INSURANCE",
}


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or "").strip().lower())
    text = "".join(character for character in text if unicodedata.category(character) != "Mn")
    text = text.replace("đ", "d")
    return re.sub(r"\s+", " ", text)


NORMALIZED_METRIC_ALIASES = {
    metric: tuple(normalize_text(alias) for alias in aliases)
    for metric, aliases in METRIC_ALIASES.items()
}
GREETING_CUES_EXTRA = ("xin chao", "chao ban", "hello", "hi", "hey")
IDENTITY_CUES_EXTRA = (
    "ban la ai", "ban la tro ly gi", "tro ly gi", "gioi thieu ban",
    "ban co the giup gi", "co the hoi gi", "finsight co the giup",
    "co the giup toi nhung gi", "finsight lam duoc gi",
)

NORMALIZED_SECTOR_ALIASES = {
    sector: tuple(normalize_text(alias) for alias in aliases)
    for sector, aliases in SECTOR_ALIASES.items()
}
NORMALIZED_KNOWLEDGE_CUES = {
    document_type: tuple(normalize_text(cue) for cue in cues)
    for document_type, cues in KNOWLEDGE_CUES.items()
}


def _contains(text: str, phrase: str) -> bool:
    return bool(re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text))


def resolve_tickers(question: str) -> tuple[list[str], list[str]]:
    universe = ticker_taxonomy()
    raw_tokens = re.findall(r"(?<!\w)[A-Za-z][A-Za-z0-9_]{1,20}(?!\w)", question)
    tickers: list[str] = []
    invalid: list[str] = []
    for raw_token in raw_tokens:
        token = raw_token.upper()
        if token in TICKER_TOKEN_EXCLUSIONS:
            continue
        if token in universe and token not in tickers:
            tickers.append(token)
        elif re.fullmatch(r"[A-Z][A-Z0-9_]{2,20}", raw_token) and token not in invalid:
            invalid.append(token)
    return tickers, invalid


def resolve_metrics(question: str) -> list[str]:
    text = normalize_text(question)
    candidates: list[tuple[int, int, str]] = []
    for metric, aliases in NORMALIZED_METRIC_ALIASES.items():
        for alias in aliases:
            match = re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", text)
            if match:
                candidates.append((match.start(), match.end(), metric))
    # Prefer the longest explicit alias so "lợi nhuận trước thuế" is not net_profit.
    selected: list[tuple[int, int, str]] = []
    for start, end, metric in sorted(candidates, key=lambda item: (-(item[1] - item[0]), item[0])):
        if any(not (end <= old_start or start >= old_end) for old_start, old_end, _ in selected):
            continue
        selected.append((start, end, metric))
    return sorted({metric for _, _, metric in selected})


def resolve_years(question: str) -> dict:
    years = [int(value) for value in re.findall(r"(?<!\d)((?:19|20)\d{2})(?!\d)", question)]
    unique_years = list(dict.fromkeys(years))
    normalized = normalize_text(question)
    explicit_range = bool(
        len(unique_years) == 2
        and (
            any(_contains(normalized, normalize_text(cue)) for cue in RANGE_CUES)
            or re.search(r"(?:19|20)\d{2}\s*[-–—]\s*(?:19|20)\d{2}", question)
        )
    )
    return {
        "years": unique_years,
        "is_range": explicit_range,
        "start_year": unique_years[0] if explicit_range else None,
        "end_year": unique_years[1] if explicit_range else None,
    }


def resolve_sector(question: str) -> str | None:
    text = normalize_text(question)
    matches: list[tuple[int, str]] = []
    for sector, aliases in NORMALIZED_SECTOR_ALIASES.items():
        for alias in aliases:
            if _contains(text, alias):
                matches.append((len(alias), sector))
    return max(matches)[1] if matches else None


def resolve_knowledge_types(question: str) -> list[str]:
    text = normalize_text(question)
    return [
        document_type
        for document_type, cues in NORMALIZED_KNOWLEDGE_CUES.items()
        if any(_contains(text, cue) for cue in cues)
    ]


def _plan(
    status: str,
    intent: str,
    *,
    queries: list[dict] | None = None,
    tickers: list[str] | None = None,
    metrics: list[str] | None = None,
    years: list[int] | None = None,
    sector: str | None = None,
    warnings: list[str] | None = None,
    errors: list[dict] | None = None,
    needs_clarification: bool = False,
) -> dict:
    return {
        "status": status,
        "intent": intent,
        "queries": queries or [],
        "entities": {
            "tickers": tickers or [],
            "metrics": metrics or [],
            "years": years or [],
            "sector": sector,
        },
        "warnings": warnings or [],
        "errors": errors or [],
        "needs_clarification": needs_clarification,
    }


def _clarification(
    intent: str, code: str, message: str, *, tickers: list[str],
    metrics: list[str], years: list[int], sector: str | None,
) -> dict:
    return _plan(
        "NEEDS_CLARIFICATION", intent, tickers=tickers, metrics=metrics,
        years=years, sector=sector, needs_clarification=True,
        errors=[{"code": code, "message": message}],
    )


def _knowledge_query_text(question: str) -> str:
    clauses = re.split(r"\s+và\s+", question, flags=re.IGNORECASE)
    for clause in clauses:
        if resolve_knowledge_types(clause):
            return clause.strip(" ?.!")
    return question.strip()


def _split_compound_question(question: str) -> list[str]:
    """Split only explicit request boundaries, never a normal comparison "A và B"."""
    parts = re.split(
        r"\s*(?:;|\n+|\?\s+(?=\S)|"
        r"\s+(?:và|rồi)\s+(?=(?:hãy|cho\s+biết|xếp\s+hạng|đánh\s+giá|"
        r"phân\s+tích|tính|liệt\s+kê|tra\s+cứu)\b)|\s+sau\s+đó\s+)\s*",
        question,
        flags=re.IGNORECASE,
    )
    return [part.strip(" .?!") for part in parts if part.strip(" .?!")]


def _multi_query_plan(original: str, clauses: list[str]) -> dict:
    subplans = [create_query_plan(clause) for clause in clauses]
    first_failure = next((plan for plan in subplans if plan.get("status") != "OK"), None)
    if first_failure is not None:
        failed_index = subplans.index(first_failure) + 1
        plan = _plan(
            first_failure.get("status", "NEEDS_CLARIFICATION"),
            "MULTI_QUERY",
            tickers=first_failure.get("entities", {}).get("tickers", []),
            metrics=first_failure.get("entities", {}).get("metrics", []),
            years=first_failure.get("entities", {}).get("years", []),
            sector=first_failure.get("entities", {}).get("sector"),
            needs_clarification=True,
            errors=[
                {
                    **error,
                    "message": f"Yêu cầu thứ {failed_index}: {error.get('message', '')}",
                }
                for error in first_failure.get("errors", [])
            ],
        )
        plan["subplans"] = subplans
        plan["clauses"] = clauses
        return plan

    entities = [plan.get("entities", {}) for plan in subplans]
    plan = _plan(
        "OK",
        "MULTI_QUERY",
        queries=[query for subplan in subplans for query in subplan.get("queries", [])],
        tickers=list(dict.fromkeys(ticker for entity in entities for ticker in entity.get("tickers", []))),
        metrics=list(dict.fromkeys(metric for entity in entities for metric in entity.get("metrics", []))),
        years=list(dict.fromkeys(year for entity in entities for year in entity.get("years", []))),
        warnings=[warning for subplan in subplans for warning in subplan.get("warnings", [])],
    )
    plan["subplans"] = subplans
    plan["clauses"] = clauses
    return plan


def create_query_plan(question: Any) -> dict:
    """Create a deterministic plan; no tool execution occurs here."""
    original = str(question or "").strip()
    if not original:
        return _clarification(
            "UNKNOWN", "EMPTY_QUESTION", "Câu hỏi không được để trống.",
            tickers=[], metrics=[], years=[], sector=None,
        )

    clauses = _split_compound_question(original)
    if len(clauses) > 1:
        return _multi_query_plan(original, clauses)

    normalized = normalize_text(original)
    tickers, invalid_tickers = resolve_tickers(original)
    metrics = resolve_metrics(original)
    time = resolve_years(original)
    years = time["years"]
    sector = resolve_sector(original)
    knowledge_types = resolve_knowledge_types(original)
    has_rank_cue = any(_contains(normalized, normalize_text(cue)) for cue in RANK_CUES)
    has_compare_cue = any(_contains(normalized, normalize_text(cue)) for cue in COMPARE_CUES)
    has_trend_cue = any(_contains(normalized, normalize_text(cue)) for cue in TREND_CUES)
    has_evaluation_cue = any(
        _contains(normalized, normalize_text(cue)) for cue in EVALUATION_CUES
    )
    has_generic_stock_cue = any(
        _contains(normalized, normalize_text(cue)) for cue in GENERIC_STOCK_CUES
    )
    has_greeting_cue = any(_contains(normalized, cue) for cue in GREETING_CUES_EXTRA)
    has_identity_cue = any(_contains(normalized, cue) for cue in IDENTITY_CUES_EXTRA)

    # Handle greetings locally; they never need PostgreSQL, Qdrant, embeddings,
    # or an LLM call.
    if (
        (has_greeting_cue or has_identity_cue)
        and not tickers
        and not invalid_tickers
        and not metrics
        and not years
        and not knowledge_types
        and not has_rank_cue
        and not has_compare_cue
        and not has_trend_cue
    ):
        return _plan("OK", "GREETING")

    has_meaningful_signal = any((
        tickers,
        invalid_tickers,
        metrics,
        years,
        knowledge_types,
        has_rank_cue,
        has_compare_cue,
        has_trend_cue,
        has_evaluation_cue,
        has_generic_stock_cue,
        has_greeting_cue,
        has_identity_cue,
        sector,
    ))
    if not has_meaningful_signal:
        return _plan(
            "UNKNOWN", "UNKNOWN", needs_clarification=True,
            errors=[{
                "code": "GIBBERISH_OR_UNSUPPORTED",
                "message": "Câu hỏi không chứa yêu cầu tài chính hoặc doanh nghiệp có thể nhận diện.",
            }],
        )

    if invalid_tickers and not tickers:
        return _plan(
            "INVALID_TICKER", "UNKNOWN", tickers=invalid_tickers, metrics=metrics,
            years=years, sector=sector, needs_clarification=True,
            errors=[{
                "code": "INVALID_TICKER",
                "message": f"Ticker không thuộc universe được duyệt: {invalid_tickers}",
            }],
        )
    if len(metrics) > 1:
        return _clarification(
            "UNKNOWN", "AMBIGUOUS_METRIC",
            f"Câu hỏi khớp nhiều metric: {metrics}", tickers=tickers,
            metrics=metrics, years=years, sector=sector,
        )
    metric = metrics[0] if metrics else None
    has_percent_growth_cue = any(cue in normalized for cue in PERCENT_GROWTH_CUES)
    if has_percent_growth_cue and metric in YOY_GROWTH_BY_BASE_METRIC:
        metric = YOY_GROWTH_BY_BASE_METRIC[metric]
        metrics = [metric]

    if has_rank_cue:
        if metric is None:
            return _clarification(
                "RANK", "MISSING_METRIC", "Cần cung cấp metric để xếp hạng.",
                tickers=tickers, metrics=metrics, years=years, sector=sector,
            )
        if len(years) != 1:
            return _clarification(
                "RANK", "MISSING_YEAR", "Cần cung cấp đúng một năm để xếp hạng.",
                tickers=tickers, metrics=metrics, years=years, sector=sector,
            )
        if sector is None:
            return _clarification(
                "RANK", "MISSING_SECTOR", "Cần cung cấp sector để xếp hạng.",
                tickers=tickers, metrics=metrics, years=years, sector=sector,
            )
        low = any(_contains(normalized, normalize_text(cue)) for cue in LOW_DIRECTION_CUES)
        high = any(_contains(normalized, normalize_text(cue)) for cue in HIGH_DIRECTION_CUES)
        has_top = _contains(normalized, "top")
        has_bottom = _contains(normalized, "bottom")
        if low and high:
            return _clarification(
                "RANK", "AMBIGUOUS_DIRECTION", "Chiều xếp hạng không rõ ràng.",
                tickers=tickers, metrics=metrics, years=years, sector=sector,
            )
        direction_defaulted = not low and not high and not has_top and not has_bottom
        limit_match = re.search(
            r"(?<!\w)(?:top|bottom|rank|xep hang)\s*(\d+)(?!\w)",
            normalized,
        )
        entity_limit_match = re.search(
            r"(?<!\w)(\d{1,3})\s+(?:doanh nghiep|ngan hang|ma co phieu|co phieu)(?!\w)",
            normalized,
        )
        leading_limit_match = re.match(r"^\s*(\d{1,3})(?=\s)", normalized)
        limit = (
            int(limit_match.group(1)) if limit_match
            else int(entity_limit_match.group(1)) if entity_limit_match
            else int(leading_limit_match.group(1)) if leading_limit_match
            else 10
        )
        query = {
            "query_type": "RANK",
            "params": {
                "metric": metric, "year": years[0], "sector": sector,
                # "top" alone is explicitly documented as descending; an explicit
                # "thấp nhất/nhỏ nhất" takes precedence and selects ascending.
                "limit": limit, "descending": not low,
            },
        }
        if sector not in {"CORPORATE", "BANK"}:
            return _plan(
                "UNSUPPORTED_FOR_MVP", "RANK", queries=[query], tickers=tickers,
                metrics=metrics, years=years, sector=sector,
                errors=[{
                    "code": "UNSUPPORTED_FOR_MVP",
                    "message": f"Ranking numerical chưa hỗ trợ sector {sector}.",
                }],
            )
        return _plan(
            "OK", "RANK", queries=[query], tickers=tickers,
            metrics=metrics, years=years, sector=sector,
            warnings=["RANK_DIRECTION_DEFAULTED_DESC"] if direction_defaulted else [],
        )

    if has_evaluation_cue:
        if len(tickers) != 1:
            return _clarification(
                "EVALUATION", "MISSING_TICKER",
                "Đánh giá cần đúng một mã cổ phiếu.", tickers=tickers,
                metrics=metrics, years=years, sector=sector,
            )
        if len(years) > 1:
            return _clarification(
                "EVALUATION", "INVALID_PERIOD",
                "Đánh giá chỉ nhận một năm hoặc tự chọn năm mới nhất có dữ liệu.",
                tickers=tickers, metrics=metrics, years=years, sector=sector,
            )
        return _plan(
            "OK", "EVALUATION", tickers=tickers, metrics=metrics,
            years=years, sector=sector, queries=[{
                "query_type": "EVALUATION",
                "params": {
                    "ticker": tickers[0],
                    "year": years[0] if years else None,
                },
            }],
        )

    # A short request such as "cổ phiếu MBB" is understood as a request for
    # the company profile. Explicit financial/ranking/comparison cues retain
    # their more specific routes above and below.
    if (
        has_generic_stock_cue
        and len(tickers) == 1
        and metric is None
        and not knowledge_types
        and not has_compare_cue
        and not has_trend_cue
    ):
        knowledge_types = ["company_profile"]

    has_knowledge = bool(knowledge_types)
    if has_knowledge and metric is not None:
        if len(tickers) != 1:
            return _clarification(
                "HYBRID", "MISSING_TICKER", "HYBRID cần đúng một ticker.",
                tickers=tickers, metrics=metrics, years=years, sector=sector,
            )
        if len(years) != 1:
            return _clarification(
                "HYBRID", "MISSING_YEAR", "Phần financial cần đúng một năm.",
                tickers=tickers, metrics=metrics, years=years, sector=sector,
            )
        queries = [
            {
                "query_type": "COMPANY_KNOWLEDGE",
                "params": {
                    "ticker": tickers[0], "query": _knowledge_query_text(original),
                    "document_types": knowledge_types, "top_k": 3,
                },
            },
            {
                "query_type": "FACT",
                "params": {"ticker": tickers[0], "metric": metric, "year": years[0]},
            },
        ]
        return _plan("OK", "HYBRID", queries=queries, tickers=tickers,
                     metrics=metrics, years=years, sector=sector)

    if has_compare_cue:
        if len(tickers) == 1 and len(years) == 2:
            if metric is None:
                return _clarification(
                    "COMPARE", "MISSING_METRIC", "COMPARE cần một metric.",
                    tickers=tickers, metrics=metrics, years=years, sector=sector,
                )
            if metric in YOY_GROWTH_METRICS:
                target_year, comparison_year = years
                if target_year != comparison_year + 1:
                    return _clarification(
                        "FACT", "INVALID_PERIOD",
                        "Tăng trưởng theo năm cần năm đích liền sau năm so sánh.",
                        tickers=tickers, metrics=metrics, years=years, sector=sector,
                    )
                return _plan(
                    "OK", "FACT", tickers=tickers, metrics=metrics, years=years,
                    sector=sector, queries=[{
                        "query_type": "FACT",
                        "params": {
                            "ticker": tickers[0], "metric": metric,
                            "year": target_year,
                        },
                    }],
                )
            start_year, end_year = sorted(years)
            return _plan(
                "OK", "TIME_SERIES", tickers=tickers, metrics=metrics,
                years=years, sector=sector, queries=[{
                    "query_type": "TIME_SERIES",
                    "params": {
                        "ticker": tickers[0], "metric": metric,
                        "start_year": start_year, "end_year": end_year,
                    },
                }],
            )
        if len(tickers) < 2:
            return _clarification(
                "COMPARE", "MISSING_TICKERS", "COMPARE cần ít nhất hai ticker.",
                tickers=tickers, metrics=metrics, years=years, sector=sector,
            )
        if metric is None:
            return _clarification(
                "COMPARE", "MISSING_METRIC", "COMPARE cần một metric.",
                tickers=tickers, metrics=metrics, years=years, sector=sector,
            )
        if len(years) != 1:
            return _clarification(
                "COMPARE", "MISSING_YEAR", "COMPARE cần đúng một năm.",
                tickers=tickers, metrics=metrics, years=years, sector=sector,
            )
        return _plan(
            "OK", "COMPARE", tickers=tickers, metrics=metrics, years=years,
            sector=sector, queries=[{
                "query_type": "COMPARE",
                "params": {"tickers": tickers, "metric": metric, "year": years[0]},
            }],
        )

    if time["is_range"] or has_trend_cue:
        if len(tickers) != 1:
            return _clarification(
                "TIME_SERIES", "MISSING_TICKER", "TIME_SERIES cần đúng một ticker.",
                tickers=tickers, metrics=metrics, years=years, sector=sector,
            )
        if metric is None:
            return _clarification(
                "TIME_SERIES", "MISSING_METRIC", "TIME_SERIES cần một metric.",
                tickers=tickers, metrics=metrics, years=years, sector=sector,
            )
        if not time["is_range"]:
            return _clarification(
                "TIME_SERIES", "MISSING_PERIOD", "Cần cung cấp khoảng năm rõ ràng.",
                tickers=tickers, metrics=metrics, years=years, sector=sector,
            )
        if time["start_year"] > time["end_year"]:
            return _clarification(
                "TIME_SERIES", "INVALID_PERIOD", "Năm bắt đầu phải không lớn hơn năm kết thúc.",
                tickers=tickers, metrics=metrics, years=years, sector=sector,
            )
        return _plan(
            "OK", "TIME_SERIES", tickers=tickers, metrics=metrics, years=years,
            sector=sector, queries=[{
                "query_type": "TIME_SERIES",
                "params": {
                    "ticker": tickers[0], "metric": metric,
                    "start_year": time["start_year"], "end_year": time["end_year"],
                },
            }],
        )

    if metric is not None:
        if len(tickers) != 1:
            return _clarification(
                "FACT", "MISSING_TICKER", "FACT cần đúng một ticker.",
                tickers=tickers, metrics=metrics, years=years, sector=sector,
            )
        if len(years) != 1:
            return _clarification(
                "FACT", "MISSING_YEAR", "Một năm cụ thể cần được cung cấp.",
                tickers=tickers, metrics=metrics, years=years, sector=sector,
            )
        return _plan(
            "OK", "FACT", tickers=tickers, metrics=metrics, years=years,
            sector=sector, queries=[{
                "query_type": "FACT",
                "params": {"ticker": tickers[0], "metric": metric, "year": years[0]},
            }],
        )

    if has_knowledge:
        if len(tickers) != 1:
            return _clarification(
                "COMPANY_KNOWLEDGE", "MISSING_TICKER",
                "COMPANY_KNOWLEDGE cần đúng một ticker.", tickers=tickers,
                metrics=metrics, years=years, sector=sector,
            )
        return _plan(
            "OK", "COMPANY_KNOWLEDGE", tickers=tickers, metrics=metrics,
            years=years, sector=sector, queries=[{
                "query_type": "COMPANY_KNOWLEDGE",
                "params": {
                    "ticker": tickers[0], "query": original,
                    "document_types": knowledge_types, "top_k": 3,
                },
            }],
        )

    return _plan(
        "UNKNOWN", "UNKNOWN", tickers=tickers, metrics=metrics, years=years,
        sector=sector, needs_clarification=True,
        errors=[{
            "code": "UNKNOWN_INTENT",
            "message": "Không thể tạo kế hoạch deterministic an toàn cho câu hỏi này.",
        }],
    )
