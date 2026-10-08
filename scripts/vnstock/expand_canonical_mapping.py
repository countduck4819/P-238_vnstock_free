"""Prepare deterministic full-universe mapping candidates.

Default mode inspects only the review sample (FPT, ACB, SSI, BVH).  The
explicit ``--all`` flag is reserved for a human-run terminal batch and is not
executed by the coding agent.
"""

from __future__ import annotations

import argparse
import csv
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "vnstock" / "raw" / "financial"
META = ROOT / "data" / "vnstock" / "metadata"
OUTPUT = META / "canonical_mapping_expansion_candidates.csv"
SAMPLE = ("FPT", "ACB", "SSI", "BVH")
CORPORATE = {"FPT", "HPG", "MWG", "GAS"}
BANK = {"ACB", "MBB"}
TARGETS = {
    "net_revenue": ("income_statement", ("net sales", "net revenue", "doanh thu thuan", "doanh thu")),
    "profit_before_tax": ("income_statement", ("net accounting profit loss before tax", "profit before tax", "loi nhuan truoc thue")),
    "net_profit": ("income_statement", ("net profit loss after tax", "net profit", "profit after tax", "loi nhuan sau thue")),
    "total_assets": ("balance_sheet", ("total assets", "tong tai san")),
    "total_liabilities": ("balance_sheet", ("liabilities", "total liabilities", "tong no phai tra")),
    "total_equity": ("balance_sheet", ("owners equity", "total equity", "shareholders equity", "von chu so huu")),
    "operating_cash_flow": ("cash_flow", ("net cash flows from operating activities", "operating cash flow", "luu chuyen tien thuan tu hoat dong kinh doanh")),
    "net_interest_income": ("income_statement", ("net interest income", "thu nhap lai thuan")),
    "net_fee_and_commission_income": ("income_statement", ("net fee and commission income", "lai lo thuan tu hoat dong dich vu")),
    "operating_expenses": ("income_statement", ("operating expenses", "chi phi hoat dong")),
    "provision_for_credit_losses": ("income_statement", ("provision for credit losses", "du phong ton that tin dung")),
}


def norm(value: object) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def tickers() -> list[str]:
    with (META / "tickers.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        return sorted({row["ticker"].strip().upper() for row in csv.DictReader(handle) if row.get("ticker", "").strip()})


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover deterministic canonical mapping candidates")
    parser.add_argument("--all", action="store_true", help="Prepare all tickers (human terminal only; not run by agent)")
    parser.add_argument("--only", help="Comma-separated ticker sample")
    args = parser.parse_args()
    selected = [value.strip().upper() for value in args.only.split(",") if value.strip()] if args.only else (tickers() if args.all else list(SAMPLE))
    if not args.all and not args.only:
        selected = list(SAMPLE)
    invalid = sorted(set(selected) - set(tickers()))
    if invalid: raise SystemExit(f"Unknown tickers: {', '.join(invalid)}")
    records = []
    for ticker in selected:
        if ticker in CORPORATE: targets = {key for key in TARGETS if key in {"net_revenue", "profit_before_tax", "net_profit", "total_assets", "total_liabilities", "total_equity", "operating_cash_flow"}}
        elif ticker in BANK: targets = {key for key in TARGETS if key in {"net_interest_income", "net_fee_and_commission_income", "operating_expenses", "provision_for_credit_losses", "profit_before_tax", "net_profit", "total_assets", "total_liabilities", "total_equity"}}
        else: targets = set(TARGETS)  # inspect-only candidates; no automatic approval for securities/insurance
        frames = {}
        for statement in sorted({TARGETS[key][0] for key in targets}):
            path = RAW / ticker / f"{statement}.parquet"
            if path.exists(): frames[statement] = pd.read_parquet(path)
        for canonical in sorted(targets):
            statement, aliases = TARGETS[canonical]
            frame = frames.get(statement)
            candidates = []
            if frame is not None and "item_id" in frame.columns:
                alias_set = {norm(alias) for alias in aliases}
                for index, row in frame.iterrows():
                    labels = {norm(row.get(column)) for column in ("item_id", "item", "item_en")}
                    if labels & alias_set:
                        years = [column for column in frame.columns if str(column).strip().isdigit()]
                        candidates.append((index, row, years))
            source_rows = {int(index) for index, _, _ in candidates}
            status = "UNMAPPED" if not candidates else "AMBIGUOUS" if len(source_rows) > 1 else "APPROVED"
            # Securities and insurance are discovery-only in this phase; even a
            # deterministic label match must remain UNMAPPED for human review.
            if ticker not in CORPORATE and ticker not in BANK:
                status = "UNMAPPED" if status == "APPROVED" else status
            if not candidates:
                candidates = [("", {"item_id": "", "item": "", "item_en": ""}, [])]
            for index, row, years in candidates:
                records.append({"ticker": ticker, "canonical_metric_code": canonical, "statement_type": statement, "source_item_id": row.get("item_id", ""), "source_item_name": row.get("item", ""), "source_item_name_en": row.get("item_en", ""), "source_row_index": index, "years_available": str(sorted(int(str(year).strip()) for year in years)), "candidate_count": len(candidates) if status != "UNMAPPED" or source_rows else 0, "distinct_source_rows": len(source_rows), "candidate_status": status, "mapping_scope": "ticker", "notes": "Automatic approval is prohibited; review semantic labels and collisions before mapping."})
    with OUTPUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0])); writer.writeheader(); writer.writerows(records)
    print(f"Wrote {len(records)} candidates for {len(selected)} ticker(s): {OUTPUT}")
    return 0


if __name__ == "__main__": raise SystemExit(main())
