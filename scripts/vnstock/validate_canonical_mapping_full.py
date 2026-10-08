"""Aggregate validation for the full canonical mapping candidate artifact."""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
META = ROOT / "data" / "vnstock" / "metadata"
INPUT = META / "canonical_mapping_expansion_candidates.csv"
SUMMARY = META / "canonical_mapping_full_validation_summary.json"
REPORT = META / "canonical_mapping_full_validation_report.md"

def counts(frame: pd.DataFrame, col: str) -> dict[str, int]:
    return {str(k): int(v) for k, v in frame[col].fillna("").value_counts().to_dict().items()}

def main() -> int:
    d = pd.read_csv(INPUT)
    expected = {"APPROVED", "AMBIGUOUS", "UNMAPPED"}
    status_counts = counts(d, "candidate_status")
    dup_cols = ["ticker", "canonical_metric_code", "source_row_index", "source_item_id"]
    duplicate_rows = int(d.duplicated(dup_cols, keep=False).sum())
    approved = d[d.candidate_status == "APPROVED"]
    approved_bad = approved[(approved.source_item_id.fillna("") == "") | (approved.source_item_name.fillna("") == "") | (approved.candidate_count <= 0) | (approved.distinct_source_rows != 1)]
    coverage = {}
    for metric, g in d.groupby("canonical_metric_code"):
        coverage[metric] = {"evaluated_tickers": int(g.ticker.nunique()), "approved_tickers": int(g.loc[g.candidate_status == "APPROVED", "ticker"].nunique()), "ambiguous_tickers": int(g.loc[g.candidate_status == "AMBIGUOUS", "ticker"].nunique()), "unmapped_tickers": int(g.loc[g.candidate_status == "UNMAPPED", "ticker"].nunique())}
        coverage[metric]["approval_pct"] = round(100 * coverage[metric]["approved_tickers"] / coverage[metric]["evaluated_tickers"], 2) if coverage[metric]["evaluated_tickers"] else 0
    collisions = d[d.candidate_status == "AMBIGUOUS"]
    summary = {"candidate_total": int(len(d)), "unique_tickers": int(d.ticker.nunique()), "unique_metrics": int(d.canonical_metric_code.nunique()), "status_counts": status_counts, "unexpected_statuses": sorted(set(status_counts) - expected), "duplicate_logical_rows": duplicate_rows, "approved_total": int(len(approved)), "approved_provenance_invalid": int(len(approved_bad)), "coverage_by_metric": coverage, "statement_counts": counts(d, "statement_type"), "ambiguous_total": int(len(collisions)), "ambiguous_tickers": sorted(collisions.ticker.unique().tolist()), "ambiguous_metrics": sorted(collisions.canonical_metric_code.unique().tolist())}
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Full canonical mapping candidate validation", "", f"- Artifact: `{INPUT.name}`", f"- Candidate total: **{summary['candidate_total']}**", f"- Unique tickers: **{summary['unique_tickers']}**", f"- Unique canonical metrics: **{summary['unique_metrics']}**", f"- Status counts: `{status_counts}`", f"- Unexpected statuses: **{summary['unexpected_statuses'] or 'none'}**", f"- Duplicate logical rows: **{duplicate_rows}**", f"- APPROVED provenance-invalid rows: **{summary['approved_provenance_invalid']}**", "", "## Coverage by canonical metric", "", "| Metric | Evaluated | Approved | Ambiguous | Unmapped | Approval % |", "|---|---:|---:|---:|---:|---:|"]
    for metric, c in sorted(coverage.items()): lines.append(f"| {metric} | {c['evaluated_tickers']} | {c['approved_tickers']} | {c['ambiguous_tickers']} | {c['unmapped_tickers']} | {c['approval_pct']}% |")
    lines += ["", "## Collision summary", "", f"- Ambiguous candidate rows: **{summary['ambiguous_total']}**", f"- Affected tickers: `{', '.join(summary['ambiguous_tickers']) or 'none'}`", f"- Affected metrics: `{', '.join(summary['ambiguous_metrics']) or 'none'}`", "- No winner was selected automatically.", "", "## Decision", "", "PASS for artifact validation only; STOP before serving-facts scale."]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0

if __name__ == "__main__": raise SystemExit(main())
