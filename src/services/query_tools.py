"""Deterministic query tools over PostgreSQL serving facts and Qdrant knowledge."""
from __future__ import annotations

import csv
import json
import os
import re
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.services.derived_metrics import calculate

ROOT = Path(__file__).resolve().parents[2]
META = ROOT / "data" / "vnstock" / "metadata"
TAXONOMY = META / "financial_sector_taxonomy.csv"
EMBEDDING_CONFIG = META / "company_knowledge_embedding_config.json"

BASE_METRICS = {
    "CORPORATE": {
        "net_profit", "net_revenue", "profit_before_tax",
        "total_assets", "total_liabilities",
    },
    "BANK": {
        "net_fee_and_commission_income", "net_interest_income", "net_profit",
        "profit_before_tax", "provision_for_credit_losses", "total_assets",
        "total_equity",
    },
}
DERIVED_METRICS = {
    "net_revenue_yoy_growth": {"CORPORATE"},
    "net_profit_yoy_growth": {"CORPORATE", "BANK"},
    "net_profit_margin": {"CORPORATE"},
    "roa": {"CORPORATE", "BANK"},
    "roe": {"BANK"},
}
EVALUATION_METRICS = {
    "CORPORATE": (
        "net_revenue", "net_profit", "profit_before_tax", "total_assets",
        "total_liabilities", "net_revenue_yoy_growth",
        "net_profit_yoy_growth", "net_profit_margin", "roa",
    ),
    "BANK": (
        "net_interest_income", "net_fee_and_commission_income", "net_profit",
        "profit_before_tax", "provision_for_credit_losses", "total_assets",
        "total_equity", "net_profit_yoy_growth", "roa", "roe",
    ),
}
METRIC_ALIASES = {code: code for code in set().union(*BASE_METRICS.values(), DERIVED_METRICS)}
DOCUMENT_TYPES = {"company_profile", "company_history", "management", "listing_info"}


@lru_cache(maxsize=1)
def ticker_taxonomy() -> dict[str, str]:
    with TAXONOMY.open(encoding="utf-8", newline="") as handle:
        return {
            row["ticker"].strip().upper(): row["financial_sector_family"].strip().upper()
            for row in csv.DictReader(handle)
            if row.get("status", "APPROVED").strip().upper() == "APPROVED"
        }


def database_url() -> str:
    if os.environ.get("FINANCIAL_DATABASE_URL"):
        return os.environ["FINANCIAL_DATABASE_URL"]
    # Keep compatibility with the project's existing DATABASE_URL convention.
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    match = re.search(
        r"^FINANCIAL_DATABASE_URL\s*=\s*(.*)$",
        (ROOT / ".env").read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if match:
        return match.group(1).strip().strip("\"'")
    match = re.search(
        r"^DATABASE_URL\s*=\s*(.*)$",
        (ROOT / ".env").read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if not match:
        raise RuntimeError("FINANCIAL_DATABASE_URL is not configured")
    return match.group(1).strip().strip("\"'")


def configured_value(name: str) -> str | None:
    """Read a setting from the process environment or the project .env file."""
    value = os.environ.get(name)
    if value:
        return value.strip().strip("\"'")
    env_file = ROOT / ".env"
    if not env_file.exists():
        return None
    match = re.search(rf"^\s*{re.escape(name)}\s*=\s*(.*)$", env_file.read_text(encoding="utf-8"), re.MULTILINE)
    return match.group(1).strip().strip("\"'") if match else None


def result(
    tool: str,
    status: str,
    *,
    ticker: str | None = None,
    tickers: list[str] | None = None,
    metric: str | None = None,
    year: int | None = None,
    period: dict[str, int] | None = None,
    sector: str | None = None,
    data: list[dict] | None = None,
    source: str | None = None,
    provenance: list[dict] | None = None,
    errors: list[dict] | None = None,
    warnings: list[str] | None = None,
) -> dict:
    """Return the same compact top-level contract for every tool."""
    return {
        "tool": tool,
        "status": status,
        "ticker": ticker,
        "tickers": tickers or [],
        "metric": metric,
        "year": year,
        "period": period,
        "sector": sector,
        "data": data or [],
        "source": source,
        "provenance": provenance or [],
        "errors": errors or [],
        "warnings": warnings or [],
    }


class QueryTools:
    """Reusable services; PostgreSQL and BGE-M3 are both initialized lazily."""

    def __init__(self) -> None:
        self._connection = None
        self._qdrant = None
        self._embedder = None
        self._embedding_config: dict | None = None

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None
        if self._qdrant is not None and hasattr(self._qdrant, "close"):
            self._qdrant.close()
            self._qdrant = None

    def _db(self):
        if self._connection is None or self._connection.closed:
            import psycopg
            from psycopg.rows import dict_row

            self._connection = psycopg.connect(
                database_url(),
                connect_timeout=5,
                options="-c default_transaction_read_only=on",
                row_factory=dict_row,
            )
        return self._connection

    @staticmethod
    def _ticker(value: Any) -> tuple[str, str | None]:
        ticker = str(value or "").strip().upper()
        return ticker, ticker_taxonomy().get(ticker)

    @staticmethod
    def _metric(value: Any) -> str | None:
        return METRIC_ALIASES.get(str(value or "").strip().lower())

    @staticmethod
    def _metric_kind(metric: str) -> str:
        return "DERIVED" if metric in DERIVED_METRICS else "BASE"

    @staticmethod
    def _applicable(metric: str, sector: str) -> bool:
        if metric in DERIVED_METRICS:
            return sector in DERIVED_METRICS[metric]
        return metric in BASE_METRICS.get(sector, set())

    @staticmethod
    def _invalid_ticker(tool: str, ticker: str) -> dict:
        return result(
            tool, "INVALID_TICKER", ticker=ticker,
            errors=[{"code": "INVALID_TICKER", "message": "Ticker is outside the approved universe"}],
        )

    @staticmethod
    def _invalid_metric(tool: str, metric: Any, **context: Any) -> dict:
        return result(
            tool, "INVALID_METRIC", metric=str(metric or "").strip().lower(),
            errors=[{"code": "INVALID_METRIC", "message": "Metric is not in the deterministic registry"}],
            **context,
        )

    @staticmethod
    def _unsupported(tool: str, ticker: str, metric: str, sector: str, **context: Any) -> dict:
        return result(
            tool, "UNSUPPORTED", ticker=ticker, metric=metric, sector=sector,
            errors=[{"code": "UNSUPPORTED", "message": f"{metric} is not supported for {sector}"}],
            **context,
        )

    def _base_rows(
        self, ticker: str, metric_codes: Iterable[str], start_year: int, end_year: int
    ) -> list[dict]:
        codes = sorted(set(metric_codes))
        if not codes:
            return []
        rows = self._db().execute(
            """
            SELECT s.ticker, s.year, s.canonical_metric_code, s.value,
                   c.unit_type AS unit, s.source_evidence_id, s.mapping_id
            FROM financial.vnstock_serving_facts AS s
            LEFT JOIN financial.vnstock_metric_catalog AS c
              ON c.canonical_metric_code = s.canonical_metric_code
            WHERE s.ticker = %s
              AND s.canonical_metric_code = ANY(%s)
              AND s.year BETWEEN %s AND %s
            ORDER BY s.year, s.canonical_metric_code
            """,
            (ticker, codes, start_year, end_year),
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _base_data(row: dict, status: str = "OK") -> dict:
        return {
            "ticker": row["ticker"],
            "year": row["year"],
            "canonical_metric_code": row["canonical_metric_code"],
            "value": row["value"],
            "unit": row.get("unit"),
            "metric_type": "BASE",
            "status": status,
            "source_evidence_id": row.get("source_evidence_id"),
        }

    @staticmethod
    def _derived_requirements(metric: str, year: int) -> tuple[set[str], int, int]:
        if metric == "net_revenue_yoy_growth":
            return {"net_revenue"}, year - 1, year
        if metric == "net_profit_yoy_growth":
            return {"net_profit"}, year - 1, year
        if metric == "net_profit_margin":
            return {"net_profit", "net_revenue"}, year, year
        if metric == "roa":
            return {"net_profit", "total_assets"}, year - 1, year
        return {"net_profit", "total_equity"}, year - 1, year

    def get_fact(self, ticker: Any, metric: Any, year: Any) -> dict:
        tool = "get_fact"
        normalized_ticker, sector = self._ticker(ticker)
        if sector is None:
            return self._invalid_ticker(tool, normalized_ticker)
        code = self._metric(metric)
        if code is None:
            return self._invalid_metric(tool, metric, ticker=normalized_ticker, year=year)
        try:
            normalized_year = int(year)
        except (TypeError, ValueError):
            return result(tool, "INVALID_PERIOD", ticker=normalized_ticker, metric=code,
                          errors=[{"code": "INVALID_PERIOD", "message": "Year must be an integer"}])
        if not self._applicable(code, sector):
            return self._unsupported(tool, normalized_ticker, code, sector, year=normalized_year)

        if self._metric_kind(code) == "BASE":
            rows = self._base_rows(normalized_ticker, {code}, normalized_year, normalized_year)
            if not rows:
                return result(tool, "MISSING", ticker=normalized_ticker, metric=code,
                              year=normalized_year, sector=sector, source="POSTGRESQL")
            row = rows[0]
            return result(
                tool, "OK", ticker=normalized_ticker, metric=code, year=normalized_year,
                sector=sector, data=[self._base_data(row)], source="POSTGRESQL",
                provenance=[{
                    "source_evidence_id": row.get("source_evidence_id"),
                    "mapping_id": row.get("mapping_id"),
                }],
            )

        required, first_year, last_year = self._derived_requirements(code, normalized_year)
        rows = self._base_rows(normalized_ticker, required, first_year, last_year)
        facts = {(row["canonical_metric_code"], row["year"]): row["value"] for row in rows}
        derived = calculate(normalized_ticker, normalized_year, code, sector, facts)
        derived["unit"] = "ratio"
        return result(
            tool, derived["calculation_status"], ticker=normalized_ticker, metric=code,
            year=normalized_year, sector=sector, data=[derived],
            source="POSTGRESQL_DERIVED", provenance=[{
                "input_source_evidence_ids": [
                    row.get("source_evidence_id") for row in rows
                ]
            }],
        )

    def _latest_available_year(self, ticker: str) -> int | None:
        row = self._db().execute(
            """
            SELECT MAX(year) AS year
            FROM financial.vnstock_serving_facts
            WHERE ticker = %s AND value IS NOT NULL
            """,
            (ticker,),
        ).fetchone()
        return int(row["year"]) if row and row.get("year") is not None else None

    def _has_data_for_year(self, ticker: str, year: int) -> bool:
        row = self._db().execute(
            """
            SELECT 1 AS present
            FROM financial.vnstock_serving_facts
            WHERE ticker = %s AND year = %s AND value IS NOT NULL
            LIMIT 1
            """,
            (ticker, year),
        ).fetchone()
        return row is not None

    def evaluate_stock(self, ticker: Any, year: Any = None) -> dict:
        """Collect a deterministic financial snapshot for one approved ticker."""
        tool = "evaluate_stock"
        normalized_ticker, sector = self._ticker(ticker)
        if sector is None:
            return self._invalid_ticker(tool, normalized_ticker)
        if sector not in EVALUATION_METRICS:
            return result(
                tool, "UNSUPPORTED", ticker=normalized_ticker, sector=sector,
                errors=[{
                    "code": "UNSUPPORTED",
                    "message": f"Evaluation is not supported for {sector}",
                }],
            )

        year_defaulted = year in (None, "")
        if year_defaulted:
            normalized_year = self._latest_available_year(normalized_ticker)
            if normalized_year is None:
                return result(
                    tool, "NO_RESULTS", ticker=normalized_ticker, sector=sector,
                    source="POSTGRESQL",
                )
        else:
            try:
                normalized_year = int(year)
            except (TypeError, ValueError):
                return result(
                    tool, "INVALID_PERIOD", ticker=normalized_ticker, sector=sector,
                    errors=[{"code": "INVALID_PERIOD", "message": "Year must be an integer"}],
                )

        if not self._has_data_for_year(normalized_ticker, normalized_year):
            return result(
                tool, "MISSING", ticker=normalized_ticker, year=normalized_year,
                sector=sector, source="POSTGRESQL",
            )

        rows: list[dict] = []
        warnings: list[str] = []
        for metric_code in EVALUATION_METRICS[sector]:
            item = self.get_fact(normalized_ticker, metric_code, normalized_year)
            if item["status"] == "OK" and item["data"]:
                rows.append(item["data"][0])
            elif item["status"] not in {"MISSING", "MISSING_INPUT"}:
                warnings.append(f"{metric_code}: {item['status']}")

        if year_defaulted:
            warnings.insert(0, f"EVALUATION_YEAR_DEFAULTED_LATEST:{normalized_year}")
        return result(
            tool, "OK" if rows else "NO_RESULTS", ticker=normalized_ticker,
            year=normalized_year, sector=sector, data=rows,
            source="POSTGRESQL", warnings=warnings,
        )

    def get_timeseries(
        self, ticker: Any, metric: Any, start_year: Any, end_year: Any
    ) -> dict:
        tool = "get_timeseries"
        normalized_ticker, sector = self._ticker(ticker)
        if sector is None:
            return self._invalid_ticker(tool, normalized_ticker)
        code = self._metric(metric)
        if code is None:
            return self._invalid_metric(tool, metric, ticker=normalized_ticker)
        try:
            start, end = int(start_year), int(end_year)
        except (TypeError, ValueError):
            return result(tool, "INVALID_PERIOD", ticker=normalized_ticker, metric=code,
                          errors=[{"code": "INVALID_PERIOD", "message": "Years must be integers"}])
        period = {"start_year": start, "end_year": end}
        if start > end or end - start > 50:
            return result(tool, "INVALID_PERIOD", ticker=normalized_ticker, metric=code,
                          period=period, errors=[{"code": "INVALID_PERIOD", "message": "Invalid or excessive year range"}])
        if not self._applicable(code, sector):
            return self._unsupported(tool, normalized_ticker, code, sector, period=period)

        rows: list[dict] = []
        provenance: list[dict] = []
        statuses: list[str] = []
        if code in DERIVED_METRICS:
            required, first_required_year, _ = self._derived_requirements(code, start)
            base_rows = self._base_rows(normalized_ticker, required, first_required_year, end)
            facts = {
                (row["canonical_metric_code"], row["year"]): row["value"]
                for row in base_rows
            }
            provenance = [{
                "input_source_evidence_ids": [
                    row.get("source_evidence_id") for row in base_rows
                ]
            }]
            for selected_year in range(start, end + 1):
                derived = calculate(normalized_ticker, selected_year, code, sector, facts)
                derived["unit"] = "ratio"
                derived["status"] = derived["calculation_status"]
                statuses.append(derived["calculation_status"])
                rows.append(derived)
        else:
            base_rows = self._base_rows(normalized_ticker, {code}, start, end)
            by_year = {row["year"]: row for row in base_rows}
            provenance = [{
                "source_evidence_id": row.get("source_evidence_id"),
                "mapping_id": row.get("mapping_id"),
            } for row in base_rows]
            for selected_year in range(start, end + 1):
                if selected_year in by_year:
                    row = self._base_data(by_year[selected_year])
                else:
                    row = {
                        "ticker": normalized_ticker, "year": selected_year,
                        "canonical_metric_code": code, "value": None, "unit": None,
                        "metric_type": "BASE", "status": "MISSING",
                    }
                statuses.append(row["status"])
                rows.append(row)
        overall = "OK" if "OK" in statuses else (statuses[0] if statuses else "MISSING")
        missing_years = [row["year"] for row in rows if row["status"] != "OK"]
        warnings = [f"Missing or non-calculable years: {missing_years}"] if missing_years else []
        return result(
            tool, overall, ticker=normalized_ticker, metric=code, period=period,
            sector=sector, data=rows,
            source="POSTGRESQL_DERIVED" if code in DERIVED_METRICS else "POSTGRESQL",
            provenance=provenance, warnings=warnings,
        )

    def compare(self, tickers: Any, metric: Any, year: Any) -> dict:
        tool = "compare"
        if not isinstance(tickers, (list, tuple)) or not tickers:
            return result(tool, "INVALID_TICKER", metric=str(metric or ""), year=year,
                          errors=[{"code": "INVALID_TICKER", "message": "tickers must be a non-empty list"}])
        normalized = [str(ticker or "").strip().upper() for ticker in tickers]
        rows: list[dict] = []
        for ticker in normalized:
            item = self.get_fact(ticker, metric, year)
            rows.append({
                "ticker": ticker,
                "year": int(year) if str(year).isdigit() else None,
                "canonical_metric_code": item.get("metric") or self._metric(metric),
                "status": item["status"],
                "value": item["data"][0].get("value") if item["data"] else None,
                "unit": item["data"][0].get("unit") if item["data"] else None,
                "metric_type": item["data"][0].get("metric_type") if item["data"] else None,
                "provenance": item["provenance"],
            })
        code = self._metric(metric)
        overall = "OK" if any(row["status"] == "OK" for row in rows) else rows[0]["status"]
        return result(tool, overall, tickers=normalized, metric=code or str(metric),
                      year=int(year) if str(year).isdigit() else None, data=rows,
                      source="POSTGRESQL_DERIVED" if code in DERIVED_METRICS else "POSTGRESQL")

    def rank(
        self, metric: Any, year: Any, sector: Any, limit: Any, descending: bool = True
    ) -> dict:
        tool = "rank"
        code = self._metric(metric)
        normalized_sector = str(sector or "").strip().upper()
        if code is None:
            return self._invalid_metric(tool, metric, sector=normalized_sector)
        if normalized_sector not in BASE_METRICS:
            return result(tool, "UNSUPPORTED", metric=code, sector=normalized_sector,
                          errors=[{"code": "UNSUPPORTED", "message": "Sector is outside numerical MVP"}])
        if not self._applicable(code, normalized_sector):
            return result(tool, "UNSUPPORTED", metric=code, sector=normalized_sector,
                          errors=[{"code": "UNSUPPORTED", "message": f"{code} is not supported for {normalized_sector}"}])
        try:
            normalized_year, normalized_limit = int(year), int(limit)
        except (TypeError, ValueError):
            return result(tool, "INVALID_PERIOD", metric=code, sector=normalized_sector,
                          errors=[{"code": "INVALID_PERIOD", "message": "year and limit must be integers"}])
        if normalized_limit < 1 or normalized_limit > 100:
            return result(tool, "INVALID_PERIOD", metric=code, year=normalized_year,
                          sector=normalized_sector,
                          errors=[{"code": "INVALID_PERIOD", "message": "limit must be between 1 and 100"}])
        if code in DERIVED_METRICS:
            return result(tool, "UNSUPPORTED_FOR_MVP", metric=code, year=normalized_year,
                          sector=normalized_sector, source="POSTGRESQL_DERIVED",
                          errors=[{"code": "UNSUPPORTED_FOR_MVP", "message": "Derived ranking is not materialized"}])

        universe = sorted(
            ticker for ticker, family in ticker_taxonomy().items()
            if family == normalized_sector
        )
        direction = "DESC" if descending else "ASC"
        rows = self._db().execute(
            f"""
            SELECT s.ticker, s.year, s.canonical_metric_code, s.value,
                   c.unit_type AS unit, s.source_evidence_id
            FROM financial.vnstock_serving_facts AS s
            LEFT JOIN financial.vnstock_metric_catalog AS c
              ON c.canonical_metric_code = s.canonical_metric_code
            WHERE s.ticker = ANY(%s) AND s.canonical_metric_code = %s AND s.year = %s
              AND s.value IS NOT NULL
            ORDER BY s.value {direction}, s.ticker ASC
            LIMIT %s
            """,
            (universe, code, normalized_year, normalized_limit),
        ).fetchall()
        data = [dict(self._base_data(dict(row)), rank=index) for index, row in enumerate(rows, 1)]
        return result(tool, "OK" if data else "NO_RESULTS", metric=code,
                      year=normalized_year, sector=normalized_sector, data=data,
                      source="POSTGRESQL")

    def _knowledge_clients(self):
        if self._embedding_config is None:
            self._embedding_config = json.loads(EMBEDDING_CONFIG.read_text(encoding="utf-8"))
        if self._qdrant is None:
            from qdrant_client import QdrantClient

            qdrant_url = configured_value("QDRANT_URL") or self._embedding_config["qdrant_url"]
            qdrant_api_key = configured_value("QDRANT_API_KEY")
            self._qdrant = QdrantClient(
                url=qdrant_url, api_key=qdrant_api_key or None, timeout=90
            )
        if self._embedder is None:
            from sentence_transformers import SentenceTransformer

            self._embedder = SentenceTransformer(
                self._embedding_config["embedding_model"],
                revision=self._embedding_config.get("embedding_revision"),
                local_files_only=True,
            )
        return self._qdrant, self._embedder, self._embedding_config

    def search_company_knowledge(
        self, ticker: Any, query: Any, document_types: Any = None, top_k: Any = 3
    ) -> dict:
        tool = "search_company_knowledge"
        normalized_ticker, sector = self._ticker(ticker)
        if sector is None:
            return self._invalid_ticker(tool, normalized_ticker)
        text = str(query or "").strip()
        if not text:
            return result(tool, "NO_RESULTS", ticker=normalized_ticker, sector=sector,
                          source="QDRANT_QUALITATIVE",
                          errors=[{"code": "NO_RESULTS", "message": "Query is empty"}])
        try:
            limit = int(top_k)
        except (TypeError, ValueError):
            limit = 0
        if not 1 <= limit <= 20:
            return result(tool, "INVALID_PERIOD", ticker=normalized_ticker, sector=sector,
                          errors=[{"code": "INVALID_PERIOD", "message": "top_k must be between 1 and 20"}])
        selected_types = None
        if document_types is not None:
            selected_types = [str(item).strip() for item in document_types]
            invalid = sorted(set(selected_types) - DOCUMENT_TYPES)
            if not selected_types or invalid:
                return result(tool, "UNSUPPORTED", ticker=normalized_ticker, sector=sector,
                              errors=[{"code": "UNSUPPORTED", "message": f"Invalid document types: {invalid}"}])

        client, embedder, cfg = self._knowledge_clients()
        from qdrant_client import models

        must = [models.FieldCondition(
            key="ticker", match=models.MatchValue(value=normalized_ticker)
        )]
        if selected_types:
            must.append(models.FieldCondition(
                key="document_type", match=models.MatchAny(any=selected_types)
            ))
        vector = embedder.encode(
            text, show_progress_bar=False,
            normalize_embeddings=cfg["normalize_embeddings"],
        )
        points = client.query_points(
            collection_name=cfg["collection_name"], query=vector.tolist(),
            query_filter=models.Filter(must=must), limit=limit,
            with_payload=True, with_vectors=False,
        ).points
        data = []
        for point in points:
            payload = point.payload or {}
            data.append({
                "ticker": payload.get("ticker"),
                "document_id": payload.get("document_id"),
                "document_type": payload.get("document_type"),
                "score": float(point.score),
                "text": payload.get("text"),
                "source_files": payload.get("source_files"),
                "source_provider": payload.get("source_provider"),
                "as_of_date": payload.get("as_of_date"),
                "content_hash": payload.get("content_hash"),
            })
        return result(
            tool, "OK" if data else "NO_RESULTS", ticker=normalized_ticker,
            sector=sector, data=data, source="QDRANT_QUALITATIVE",
            warnings=["NUMERICAL_TRUTH_SOURCE=POSTGRESQL"],
        )
