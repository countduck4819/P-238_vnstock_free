"""Create deterministic, reviewed pilot catalog and source mappings."""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
META = ROOT / "data" / "vnstock" / "metadata"
CANDIDATES = META / "canonical_metric_candidates.csv"
CATALOG = META / "canonical_metric_catalog.csv"
MAPPINGS = META / "source_metric_mapping_pilot.csv"

PILOT = ("FPT", "HPG", "MWG", "GAS", "ACB", "MBB", "SSI", "BVH")
CORPORATE = {"FPT", "HPG", "MWG", "GAS"}
BANK = {"ACB", "MBB"}
CATALOG_ROWS = [
    ("net_revenue", "Doanh thu thuần", "Net revenue", "income_statement", "source_native_numeric", "Corporate net sales / net revenue from VCI source evidence."),
    ("net_profit", "Lợi nhuận sau thuế", "Net profit", "income_statement", "source_native_numeric", "Net profit after tax from VCI source evidence."),
    ("profit_before_tax", "Lợi nhuận trước thuế", "Profit before tax", "income_statement", "source_native_numeric", "Profit before tax from VCI source evidence."),
    ("total_assets", "Tổng tài sản", "Total assets", "balance_sheet", "source_native_numeric", "Total assets from VCI source evidence."),
    ("total_liabilities", "Tổng nợ phải trả", "Total liabilities", "balance_sheet", "source_native_numeric", "Liabilities total from VCI source evidence."),
    ("total_equity", "Vốn chủ sở hữu", "Total equity", "balance_sheet", "source_native_numeric", "Owners equity from VCI source evidence."),
    ("net_interest_income", "Thu nhập lãi thuần", "Net interest income", "income_statement", "source_native_numeric", "Bank net interest income from VCI source evidence."),
]


def mapping_id(row: dict[str, str]) -> str:
    payload = "|".join((row["ticker"], row["canonical_metric_code"], row["statement_type"], row["source_item_id"], row["source_row_index"], "v1"))
    return "map_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def main() -> int:
    with CANDIDATES.open("r", encoding="utf-8", newline="") as handle:
        candidates = list(csv.DictReader(handle))
    approved = [row for row in candidates if row["candidate_status"] == "UNIQUE"]
    # A UNIQUE candidate must have exactly one source row and all eight years.
    invalid = [row for row in approved if row["distinct_source_rows"] != "1" or len(row["years_available"].strip("[]").split(",")) != 8]
    if invalid:
        raise SystemExit(f"Invalid UNIQUE candidates: {len(invalid)}")
    with CATALOG.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["canonical_metric_code", "metric_name_vi", "metric_name_en", "statement_type", "unit_type", "description"])
        writer.writerows(CATALOG_ROWS)
    mapping_columns = ["mapping_id", "ticker_scope", "statement_type", "source", "source_item_id", "source_item_name", "source_item_name_en", "source_row_index", "canonical_metric_code", "mapping_status", "mapping_version", "row_index_dependent", "notes"]
    with MAPPINGS.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=mapping_columns)
        writer.writeheader()
        for row in approved:
            record = {
                "ticker_scope": row["ticker"], "statement_type": row["statement_type"], "source": "vnstock_vci",
                "source_item_id": row["source_item_id"], "source_item_name": row["source_item_name"], "source_item_name_en": row["source_item_name_en"],
                "source_row_index": row["source_row_index"], "canonical_metric_code": row["canonical_metric_code"], "mapping_status": "APPROVED", "mapping_version": "1",
                "row_index_dependent": "true", "notes": "Deterministic pilot mapping; source row selector required for traceability.",
            }
            record["mapping_id"] = mapping_id({"ticker": row["ticker"], **record})
            writer.writerow(record)
    print(f"Catalog metrics: {len(CATALOG_ROWS)}; approved mappings: {len(approved)}; SSI/BVH intentionally unmapped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
