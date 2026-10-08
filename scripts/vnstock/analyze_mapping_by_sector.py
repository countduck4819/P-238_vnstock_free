from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
META = ROOT / "data" / "vnstock" / "metadata"
TAX_IN = META / "tickers.csv"
TAX_OUT = META / "financial_sector_taxonomy.csv"
APPL_OUT = META / "canonical_metric_applicability.csv"
CAND = META / "canonical_mapping_expansion_candidates.csv"
ANALYSIS_OUT = META / "canonical_mapping_sector_analysis.csv"
REPORT = META / "canonical_mapping_sector_analysis_report.md"
SUMMARY = META / "canonical_mapping_sector_analysis_summary.json"
ALLOWED = {"CORPORATE", "BANK", "SECURITIES", "INSURANCE"}
CORP = {"net_revenue", "profit_before_tax", "net_profit", "total_assets", "total_liabilities", "total_equity", "operating_cash_flow"}
BANK = {"net_interest_income", "net_fee_and_commission_income", "operating_expenses", "provision_for_credit_losses", "profit_before_tax", "net_profit", "total_assets", "total_equity"}

def main() -> int:
    tax = pd.read_csv(TAX_IN, sep="\t", dtype=str).fillna("")
    tax.columns = [c.strip() for c in tax.columns]
    if set(tax.columns) != {"ticker", "TYPE"}: raise SystemExit(f"Unexpected taxonomy columns: {tax.columns.tolist()}")
    tax.ticker = tax.ticker.str.strip().str.upper(); tax.TYPE = tax.TYPE.str.strip().str.upper()
    if tax.ticker.duplicated().any() or tax.ticker.eq("").any() or (~tax.TYPE.isin(ALLOWED)).any(): raise SystemExit("Taxonomy validation failed")
    tax[["ticker", "financial_sector_family"]] = tax[["ticker", "TYPE"]].rename(columns={"TYPE":"financial_sector_family"})
    tax["classification_source"] = "user_curated_metadata"; tax["status"] = "APPROVED"
    tax[["ticker", "financial_sector_family", "classification_source", "status"]].to_csv(TAX_OUT, index=False)
    metrics = sorted(set(CORP) | set(BANK))
    rows = []
    for m in metrics:
        for s in sorted(ALLOWED):
            applicable = s == "CORPORATE" and m in CORP or s == "BANK" and m in BANK
            status = "APPROVED" if applicable else "REVIEW"
            rows.append({"canonical_metric_code":m,"financial_sector_family":s,"applicable":str(applicable).upper(),"status":status,"rule":"sector allow-list; securities/insurance require separate semantic review"})
    pd.DataFrame(rows).to_csv(APPL_OUT, index=False)
    cand = pd.read_csv(CAND, dtype=str).fillna("").merge(tax[["ticker","financial_sector_family"]], on="ticker", how="left")
    def classify(r):
        sec, metric, old = r.financial_sector_family, r.canonical_metric_code, r.candidate_status
        if old == "APPROVED": return "APPROVED"
        if sec in {"SECURITIES", "INSURANCE"}: return "UNKNOWN_REASON" if not r.source_item_id else "UNSAFE_TO_MAP"
        applicable = metric in (CORP if sec == "CORPORATE" else BANK if sec == "BANK" else set())
        if not applicable: return "NOT_APPLICABLE"
        if old == "AMBIGUOUS": return "UNSAFE_TO_MAP"
        return "NO_SOURCE_MATCH" if not r.source_item_id else "UNSAFE_TO_MAP"
    cand["analysis_status"] = cand.apply(classify, axis=1)
    cand.to_csv(ANALYSIS_OUT, index=False)
    counts = cand.analysis_status.value_counts().to_dict()
    sector = {}
    for s,g in cand.groupby("financial_sector_family"):
        sector[s] = {"ticker_count": int(tax.loc[tax.financial_sector_family.eq(s),"ticker"].nunique()), "candidate_count": int(len(g)), "approved": int((g.analysis_status=="APPROVED").sum()), "no_source_match": int((g.analysis_status=="NO_SOURCE_MATCH").sum()), "unsafe_to_map": int((g.analysis_status=="UNSAFE_TO_MAP").sum()), "not_applicable": int((g.analysis_status=="NOT_APPLICABLE").sum()), "unknown_reason": int((g.analysis_status=="UNKNOWN_REASON").sum())}
        denom = sector[s]["approved"] + sector[s]["no_source_match"] + sector[s]["unsafe_to_map"]
        sector[s]["mapping_coverage_percent"] = round(100*sector[s]["approved"]/denom,2) if denom else 0
    summary = {"taxonomy_rows":int(len(tax)),"sector_counts":tax.financial_sector_family.value_counts().to_dict(),"original_unmapped":9370,"analysis_counts":counts,"true_mapping_gap":int(counts.get("NO_SOURCE_MATCH",0)+counts.get("UNSAFE_TO_MAP",0)),"sector_breakdown":sector}
    SUMMARY.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    lines=["# Sector applicability analysis", "", f"Taxonomy: **{len(tax)}** rows; sectors: `{summary['sector_counts']}`.", "", "## Analysis status", "", "| Status | Count |", "|---|---:|"]
    lines += [f"| {k} | {v} |" for k,v in sorted(counts.items())]
    lines += ["", f"Original UNMAPPED: **9,370**", f"TRUE_MAPPING_GAP (NO_SOURCE_MATCH + UNSAFE_TO_MAP): **{summary['true_mapping_gap']}**", "", "## By sector", "", "| Sector | Tickers | Candidates | Approved | Not applicable | No source | Unsafe | Unknown | Coverage |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for s,c in sorted(sector.items()): lines.append(f"| {s} | {c['ticker_count']} | {c['candidate_count']} | {c['approved']} | {c['not_applicable']} | {c['no_source_match']} | {c['unsafe_to_map']} | {c['unknown_reason']} | {c['mapping_coverage_percent']}% |")
    lines += ["", "Securities and insurance are intentionally not assigned Corporate/Bank applicability; their source candidates remain UNKNOWN_REASON or UNSAFE_TO_MAP for manual semantic review. Total-equity collisions remain unresolved.", "", "**PASS taxonomy validation and analysis; STOP before mapping materialization.**"]
    REPORT.write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False))
    return 0
if __name__ == "__main__": raise SystemExit(main())
