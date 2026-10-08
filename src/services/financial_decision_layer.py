"""Small analyst decision layer for intent-specific, evidence-bounded conclusions.

The layer does not retrieve data or calculate financial values.  It only selects
the response contract and derives qualitative conclusions from observations that
have already been validated by the existing agent pipeline.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from src.services.intent_router import normalize_text, resolve_tickers


@dataclass(frozen=True)
class AnalystDecision:
    intent: str
    required_evidence: tuple[str, ...] = ()
    external_required: bool = False


class FinancialAnalystDecisionLayer:
    """Classify analyst intent and improve only the presentation contract."""

    COMPARISON_WEIGHTS = {
        "growth_quality": 30,
        "profitability": 30,
        "stability": 25,
        "risk": 15,
    }

    _valuation = ("dinh gia", "gia re", "re khong", "gia tri hop ly", "p/e", "pe", "p/b", "pb")
    _recent_risk = ("rui ro gan day", "risky gan day", "moi nhat", "su kien", "tin tuc", "hien tai")
    _financial_risk = (
        "rui ro tai chinh", "no vay cao", "loi nhuan co rui ro",
        "rui ro loi nhuan", "rui ro no",
    )
    _health = ("khoe len", "yeu di", "suc khoe tai chinh", "dang tang hay giam")
    _comparison = ("so sanh", "chat luong loi nhuan", "doanh nghiep nao tot hon")

    def classify(self, question: Any) -> AnalystDecision:
        text = normalize_text(question)
        if any(cue in text for cue in self._valuation):
            return AnalystDecision(
                "VALUATION_ANALYSIS",
                ("stock_price", "market_cap", "pe", "pb", "eps"),
            )
        if any(cue in text for cue in self._recent_risk):
            return AnalystDecision("RECENT_EVENT_RISK", ("external_event",), True)
        has_financial_risk = (
            any(cue in text for cue in self._financial_risk)
            or ("no vay" in text and ("cao" in text or "rui ro" in text))
            or ("loi nhuan" in text and "rui ro" in text)
        )
        if has_financial_risk:
            return AnalystDecision(
                "FINANCIAL_STATEMENT_RISK",
                ("profit_trend", "asset_trend", "liability_trend", "leverage"),
            )
        tickers, _ = resolve_tickers(str(question))
        if any(cue in text for cue in self._comparison) or len(tickers) > 1:
            return AnalystDecision(
                "COMPANY_COMPARISON",
                ("revenue_growth", "profit_growth", "net_margin", "business_quality"),
            )
        if any(cue in text for cue in self._health):
            return AnalystDecision(
                "FINANCIAL_HEALTH_ANALYSIS",
                ("revenue_growth", "profit_growth", "net_margin", "leverage"),
            )
        return AnalystDecision("FACT_LOOKUP")

    @staticmethod
    def valuation_unknown(decision: AnalystDecision, state: dict[str, Any]) -> bool:
        """Valuation is unknown unless the required valuation facts are present."""
        if decision.intent != "VALUATION_ANALYSIS":
            return False
        evidence = state.get("evidence") or []
        available = {
            str(item.get("metric") or item.get("canonical_metric_code") or "").lower()
            for item in evidence
        }
        return not {"pe", "pb", "valuation_multiple"}.intersection(available)

    def enhance(self, question: Any, state: dict[str, Any], answer: str) -> str:
        decision = self.classify(question)
        if self.valuation_unknown(decision, state):
            return (
                "<section><h3>Kết luận</h3><p>Chưa đủ dữ liệu để đánh giá định giá của mã cổ phiếu này.</p></section>"
                "<section><h3>Dữ liệu cần có</h3><ul>"
                "<li>Giá thị trường</li><li>P/E</li><li>P/B</li><li>EPS</li><li>Vốn hóa</li>"
                "</ul></section>"
            )
        if decision.intent == "FINANCIAL_HEALTH_ANALYSIS":
            health = self.health_assessment(state)
            conclusion = health["conclusion"]
            if conclusion:
                enhanced = re.sub(
                    r"(<h3>[^<]*</h3><p>).*?(</p>)",
                    rf"\1{conclusion}\2", answer, count=1, flags=re.IGNORECASE | re.DOTALL,
                )
                refs = ", ".join(health["evidence_refs"])
                if refs and "Tham chiếu bằng chứng" not in enhanced:
                    enhanced = enhanced.replace(
                        "</section>",
                        f"<p><small>Tham chiếu bằng chứng: {refs}</small></p></section>",
                        1,
                    )
                return enhanced
        if decision.intent == "COMPANY_COMPARISON":
            assessment = self.comparison_assessment(state)
            if assessment["conclusion"] and "Kết luận phân tích" not in answer:
                strengths = "".join(
                    f"<li><b>{ticker}</b>: {item}</li>"
                    for ticker, items in assessment["strengths"].items()
                    for item in items
                )
                weaknesses = "".join(
                    f"<li><b>{ticker}</b>: {item}</li>"
                    for ticker, items in assessment["weaknesses"].items()
                    for item in items
                )
                limitations = "".join(f"<li>{item}</li>" for item in assessment["limitations"])
                refs = ", ".join(assessment["evidence_refs"])
                prefix = (
                    f"<section><h3>Kết luận phân tích</h3><p>{assessment['conclusion']}</p>"
                    f"<p><small>Tham chiếu bằng chứng: {refs}</small></p></section>"
                    "<section><h3>Khung đánh giá</h3><p>Growth quality 30% · "
                    "Profitability 30% · Stability 25% · Risk 15%</p></section>"
                    f"<section><h3>Điểm mạnh</h3><ul>{strengths}</ul></section>"
                    f"<section><h3>Điểm hạn chế và rủi ro</h3><ul>{weaknesses}</ul></section>"
                )
                if limitations:
                    prefix += f"<section><h3>Hạn chế dữ liệu</h3><ul>{limitations}</ul></section>"
                return prefix + answer
        return answer

    @staticmethod
    def _evidence_items(state: dict[str, Any]) -> list[dict[str, Any]]:
        """Flatten every validated evidence representation available in state."""
        items: list[dict[str, Any]] = []
        items.extend(item for item in state.get("normalized_evidence") or [] if isinstance(item, dict))
        items.extend(item for item in state.get("derived_metrics") or [] if isinstance(item, dict))
        for item in state.get("compact_observations") or []:
            if isinstance(item, dict):
                items.append(item)
        for observation in state.get("observations") or []:
            status = getattr(observation, "status", None)
            if status != "OK":
                continue
            for row in getattr(observation, "data", []) or []:
                if isinstance(row, dict):
                    items.append({
                        **row,
                        "evidence_id": row.get("evidence_id") or row.get("source_evidence_id"),
                        "metric": row.get("canonical_metric_code") or row.get("metric") or getattr(observation, "metric", None),
                        "ticker": row.get("ticker") or getattr(observation, "ticker", None),
                    })
        return items

    def _values(self, state: dict[str, Any], metric: str) -> dict[str, list[tuple[int | None, float, str | None]]]:
        values: dict[str, list[tuple[int | None, float, str | None]]] = {}
        values = {}
        for item in self._evidence_items(state):
            code = item.get("canonical_metric_code") or item.get("metric") or item.get("name")
            if code != metric or item.get("value") is None:
                continue
            ticker = str(item.get("ticker") or "")
            try:
                year = item.get("year") if isinstance(item.get("year"), int) else None
                values.setdefault(ticker, []).append((year, float(item["value"]), item.get("evidence_id")))
            except (TypeError, ValueError):
                continue
        return values

    def health_assessment(self, state: dict[str, Any]) -> dict[str, Any]:
        """Apply health rules to normalized, compact and derived evidence."""
        revenue = self._values(state, "net_revenue")
        profit = self._values(state, "net_profit")
        margin = self._values(state, "net_profit_margin")
        ticker = next(iter(revenue or profit), None)
        refs = [
            ref for metric in (revenue, profit, margin) for rows in metric.values()
            for _, _, ref in rows if ref
        ]
        if not ticker:
            return {"conclusion": "Chưa đủ dữ liệu để kết luận doanh nghiệp khỏe lên hay yếu đi.", "evidence_refs": refs}
        rev = revenue.get(ticker, [])
        pnl = profit.get(ticker, [])
        margin_rows = margin.get(ticker, [])
        rev = sorted(rev, key=lambda item: (item[0] is None, item[0]))
        pnl = sorted(pnl, key=lambda item: (item[0] is None, item[0]))
        margin_rows = sorted(margin_rows, key=lambda item: (item[0] is None, item[0]))
        if len(rev) < 2 or len(pnl) < 2:
            # Compact/derived evidence can prove a series exists even when the
            # raw observation was compacted away by the graph.
            available = {str(item.get("metric") or item.get("name")) for item in self._evidence_items(state)}
            if not {"net_revenue", "net_profit"}.issubset(available):
                return {"conclusion": "Chưa đủ dữ liệu để kết luận doanh nghiệp khỏe lên hay yếu đi.", "evidence_refs": refs}
        rev_up = len(rev) >= 2 and rev[-1][1] > rev[0][1]
        profit_up = len(pnl) >= 2 and pnl[-1][1] > pnl[0][1]
        profit_down = len(pnl) >= 2 and pnl[-1][1] < pnl[0][1]
        margin_not_down = not margin_rows or len(margin_rows) < 2 or margin_rows[-1][1] >= margin_rows[0][1]
        if rev_up and profit_up and margin_not_down:
            conclusion = "Doanh nghiệp đang có xu hướng khỏe lên vì doanh thu, lợi nhuận và biên lợi nhuận không suy giảm trong chuỗi dữ liệu quan sát."
        elif rev_up and profit_down:
            conclusion = "Tăng trưởng chưa chuyển hóa thành hiệu quả lợi nhuận vì doanh thu tăng nhưng lợi nhuận giảm."
        elif rev_up or profit_up:
            conclusion = "Doanh nghiệp có cải thiện nhưng chưa đồng nhất giữa các chỉ tiêu tài chính."
        else:
            conclusion = "Doanh nghiệp có dấu hiệu yếu đi do các chỉ tiêu chính chưa cho thấy sự cải thiện."
        return {"conclusion": conclusion, "evidence_refs": list(dict.fromkeys(refs))}

    def _health_conclusion(self, state: dict[str, Any]) -> str | None:
        """Backward-compatible helper for callers using the previous API."""
        return self.health_assessment(state)["conclusion"]

    def _series(self, state: dict[str, Any], metric: str) -> dict[str, list[tuple[int, float, str | None]]]:
        """Return one deterministic value per ticker/year, ordered by year."""
        output: dict[str, list[tuple[int, float, str | None]]] = {}
        for ticker, rows in self._values(state, metric).items():
            by_year: dict[int, tuple[float, str | None]] = {}
            for year, value, ref in rows:
                if year is not None:
                    by_year.setdefault(year, (value, ref))
            output[ticker] = [(year, *by_year[year]) for year in sorted(by_year)]
        return output

    def comparison_assessment(self, state: dict[str, Any]) -> dict[str, Any]:
        """Compare earnings quality across dimensions without inventing evidence."""
        metrics = {
            name: self._series(state, name)
            for name in (
                "net_revenue_yoy_growth", "net_profit_yoy_growth",
                "net_profit_margin", "operating_margin", "total_assets",
                "total_liabilities", "operating_cashflow",
            )
        }
        tickers = sorted({ticker for series in metrics.values() for ticker in series})
        empty = {
            "conclusion": None, "strengths": {}, "weaknesses": {},
            "limitations": ["Chưa có đủ bằng chứng để so sánh chất lượng lợi nhuận."],
            "evidence_refs": [],
            "framework_weights": dict(self.COMPARISON_WEIGHTS),
            "dimension_leaders": {},
        }
        if len(tickers) < 2:
            return empty

        strengths = {ticker: [] for ticker in tickers}
        weaknesses = {ticker: [] for ticker in tickers}
        refs: list[str] = []
        growth_leader = self._latest_leader(metrics["net_profit_yoy_growth"], refs)
        revenue_growth_leader = self._latest_leader(metrics["net_revenue_yoy_growth"], refs)
        margin_leader = self._latest_leader(metrics["net_profit_margin"], refs)
        stability_leader = self._stability_leader(metrics["net_profit_yoy_growth"], refs)

        if growth_leader:
            strengths[growth_leader].append("Tốc độ tăng trưởng lợi nhuận gần nhất cao hơn.")
            for ticker in tickers:
                if ticker != growth_leader:
                    weaknesses[ticker].append("Tăng trưởng lợi nhuận gần nhất thấp hơn doanh nghiệp đối chiếu.")
        for ticker in tickers:
            profit_growth = metrics["net_profit_yoy_growth"].get(ticker, [])
            revenue_growth = metrics["net_revenue_yoy_growth"].get(ticker, [])
            if profit_growth and revenue_growth:
                refs.extend(ref for ref in (profit_growth[-1][2], revenue_growth[-1][2]) if ref)
                if profit_growth[-1][1] > 0 and revenue_growth[-1][1] > 0:
                    if profit_growth[-1][1] >= revenue_growth[-1][1]:
                        strengths[ticker].append("Lợi nhuận tăng nhanh hơn doanh thu, hỗ trợ chất lượng tăng trưởng.")
                    else:
                        weaknesses[ticker].append("Lợi nhuận tăng chậm hơn doanh thu, hiệu quả chuyển hóa còn hạn chế.")
        if margin_leader:
            strengths[margin_leader].append("Biên lợi nhuận ròng gần nhất cao hơn.")
            for ticker in tickers:
                if ticker != margin_leader:
                    weaknesses[ticker].append("Biên lợi nhuận ròng thấp hơn doanh nghiệp đối chiếu.")
        if stability_leader:
            strengths[stability_leader].append("Tăng trưởng lợi nhuận ổn định hơn trong chuỗi dữ liệu quan sát.")

        for ticker in tickers:
            assets = metrics["total_assets"].get(ticker, [])
            debt = metrics["total_liabilities"].get(ticker, [])
            if len(assets) >= 2 and len(debt) >= 2 and assets[0][1] and debt[0][1]:
                refs.extend(ref for _, _, ref in (*assets, *debt) if ref)
                asset_factor = assets[-1][1] / assets[0][1]
                debt_factor = debt[-1][1] / debt[0][1]
                if debt_factor > asset_factor:
                    weaknesses[ticker].append("Nợ tăng nhanh hơn tài sản, tạo tín hiệu rủi ro đòn bẩy.")

        limitations: list[str] = []
        if not metrics["operating_margin"]:
            limitations.append("Chưa có operating margin để hoàn thiện đánh giá profitability.")
        if not metrics["operating_cashflow"]:
            limitations.append("Chưa đánh giá đầy đủ chất lượng lợi nhuận theo dòng tiền do thiếu operating cashflow.")
        limitations.append("Chưa có bằng chứng định tính đủ tin cậy để kết luận mức độ chu kỳ của mô hình kinh doanh.")

        if growth_leader and margin_leader and growth_leader != margin_leader:
            conclusion = (
                f"{growth_leader} nổi bật hơn về tốc độ tăng trưởng lợi nhuận, trong khi "
                f"{margin_leader} nổi bật hơn về biên lợi nhuận. Chưa nên kết luận một doanh nghiệp "
                "có chất lượng lợi nhuận tốt hơn tuyệt đối vì các chiều đánh giá đang cho tín hiệu khác nhau."
            )
        elif growth_leader and growth_leader == margin_leader:
            conclusion = (
                f"{growth_leader} đang nổi bật hơn cả về tăng trưởng lợi nhuận và biên lợi nhuận "
                "trong phạm vi dữ liệu hiện có; kết luận vẫn cần kiểm chứng thêm bằng dòng tiền và rủi ro chu kỳ."
            )
        else:
            conclusion = "Các bằng chứng hiện có chưa đủ đồng nhất để chọn doanh nghiệp có chất lượng lợi nhuận tốt hơn."
        return {
            "conclusion": conclusion,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "limitations": limitations,
            "evidence_refs": list(dict.fromkeys(refs)),
            "framework_weights": dict(self.COMPARISON_WEIGHTS),
            "dimension_leaders": {
                "revenue_growth": revenue_growth_leader,
                "profit_growth": growth_leader,
                "net_margin": margin_leader,
                "stability": stability_leader,
            },
        }

    @staticmethod
    def _latest_leader(
        series: dict[str, list[tuple[int, float, str | None]]], refs: list[str]
    ) -> str | None:
        latest = {ticker: rows[-1] for ticker, rows in series.items() if rows}
        if len(latest) < 2:
            return None
        refs.extend(row[2] for row in latest.values() if row[2])
        return max(latest, key=lambda ticker: latest[ticker][1])

    @staticmethod
    def _stability_leader(
        series: dict[str, list[tuple[int, float, str | None]]], refs: list[str]
    ) -> str | None:
        eligible = {ticker: rows for ticker, rows in series.items() if len(rows) >= 3}
        if len(eligible) < 2:
            return None
        spreads = {
            ticker: max(row[1] for row in rows) - min(row[1] for row in rows)
            for ticker, rows in eligible.items()
        }
        leader = min(spreads, key=spreads.get)
        refs.extend(row[2] for row in eligible[leader] if row[2])
        return leader

    def _comparison_conclusion(self, state: dict[str, Any]) -> str | None:
        """Backward-compatible helper for earlier callers."""
        return self.comparison_assessment(state)["conclusion"]


__all__ = ["AnalystDecision", "FinancialAnalystDecisionLayer"]
