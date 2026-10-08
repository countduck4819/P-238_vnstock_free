"""Read-only discovery of deterministic canonical metric candidates."""

from __future__ import annotations

import argparse
import csv
import os
import re
import unicodedata
from pathlib import Path

import psycopg
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "vnstock" / "metadata" / "canonical_metric_candidates.csv"
PILOT = ("FPT", "HPG", "MWG", "GAS", "ACB", "MBB", "SSI", "BVH")
CORPORATE = {"FPT", "HPG", "MWG", "GAS"}
BANK = {"ACB", "MBB"}
TARGETS = {
    "net_revenue": {"statement_type": "income_statement", "aliases": {"net_revenue", "net revenue", "revenue", "doanh thu thuan", "doanh thu"}},
    "net_profit": {"statement_type": "income_statement", "aliases": {"net_profit", "net profit", "net profit loss after tax", "profit after tax", "profit_after_tax", "loi nhuan sau thue", "net income"}},
    "profit_before_tax": {"statement_type": "income_statement", "aliases": {"profit_before_tax", "profit before tax", "net accounting profit loss before tax", "loi nhuan truoc thue", "tong loi nhuan lo truoc thue"}},
    "total_assets": {"statement_type": "balance_sheet", "aliases": {"total_assets", "total assets", "tong tai san"}},
    "total_liabilities": {"statement_type": "balance_sheet", "aliases": {"total_liabilities", "total liabilities", "liabilities", "tong no phai tra", "no phai tra"}},
    "total_equity": {"statement_type": "balance_sheet", "aliases": {"total_equity", "total equity", "shareholders equity", "von chu so huu"}},
    "net_interest_income": {"statement_type": "income_statement", "aliases": {"net_interest_income", "net interest income", "thu nhap lai thuan"}},
}


def env_url() -> str:
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        match = re.match(r"^DATABASE_URL\s*=\s*(.*)$", line)
        if match:
            value = match.group(1).strip()
            return value[1:-1] if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'" else value
    raise SystemExit("DATABASE_URL is not configured")


def norm(value: object) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover canonical metric candidates from VCI evidence (read-only DB)")
    parser.parse_args()
    with psycopg.connect(env_url(), connect_timeout=5, options="-c default_transaction_read_only=on", row_factory=dict_row) as conn:
        rows = conn.execute("""
            SELECT ticker, statement_type, source_item_id, source_item_name, source_item_name_en,
                   year, source_row_index, value
            FROM financial.vnstock_financial_evidence
            WHERE ticker = ANY(%s)
            ORDER BY ticker, statement_type, source_item_id, source_row_index, year
        """, (list(PILOT),)).fetchall()
    output = []
    for ticker in PILOT:
        allowed = set(TARGETS)
        if ticker in CORPORATE:
            allowed.discard("net_interest_income")
        elif ticker in BANK:
            allowed.discard("net_revenue")
        else:
            # SSI/BVH are inspected but no semantics are guessed in this pilot.
            allowed = set()
        ticker_rows = [row for row in rows if row["ticker"] == ticker]
        for canonical in sorted(allowed):
            target = TARGETS[canonical]
            aliases = {norm(alias) for alias in target["aliases"]}
            candidates = [row for row in ticker_rows if row["statement_type"] == target["statement_type"] and any(norm(row[field]) in aliases for field in ("source_item_id", "source_item_name", "source_item_name_en"))]
            identities = {(row["source_item_id"], row["source_item_name"], row["source_item_name_en"], int(row["source_row_index"])) for row in candidates}
            source_rows = {int(row["source_row_index"]) for row in candidates}
            status = "MISSING" if not candidates else "UNIQUE" if len(source_rows) == 1 else "AMBIGUOUS"
            notes = "no deterministic alias match" if status == "MISSING" else "one source row selector across available years" if status == "UNIQUE" else "multiple competing source rows; no row selected"
            grouped = {}
            for row in candidates:
                key = (row["source_item_id"], row["source_item_name"], row["source_item_name_en"], int(row["source_row_index"]))
                grouped.setdefault(key, []).append(row)
            if not grouped:
                output.append({"ticker": ticker, "canonical_metric_code": canonical, "statement_type": target["statement_type"], "source_item_id": "", "source_item_name": "", "source_item_name_en": "", "source_row_index": "", "years_available": "[]", "candidate_evidence_count": 0, "distinct_source_rows": 0, "candidate_status": status, "notes": notes})
            else:
                for (item_id, item_name, item_name_en, row_index), evidence in grouped.items():
                    output.append({"ticker": ticker, "canonical_metric_code": canonical, "statement_type": target["statement_type"], "source_item_id": item_id, "source_item_name": item_name, "source_item_name_en": item_name_en, "source_row_index": row_index, "years_available": str(sorted({int(row["year"]) for row in evidence})), "candidate_evidence_count": len(evidence), "distinct_source_rows": len(source_rows), "candidate_status": status, "notes": notes})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["ticker", "canonical_metric_code", "statement_type", "source_item_id", "source_item_name", "source_item_name_en", "source_row_index", "years_available", "candidate_evidence_count", "distinct_source_rows", "candidate_status", "notes"])
        writer.writeheader(); writer.writerows(output)
    print(f"Wrote {len(output)} candidate rows to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
