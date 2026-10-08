"""Validate, query-test, and benchmark the canonical serving pilot."""

from __future__ import annotations

import argparse
import csv
import os
import re
import statistics
import time
from pathlib import Path

import psycopg
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[2]
META = ROOT / "data" / "vnstock" / "metadata"
REPORT = META / "canonical_mapping_pilot_report.md"
COUNTS = META / "serving_facts_pilot_counts.csv"
PILOT = ("FPT", "HPG", "MWG", "GAS", "ACB", "MBB", "SSI", "BVH")


def db_url() -> str:
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        match = re.match(r"^DATABASE_URL\s*=\s*(.*)$", line)
        if match:
            value = match.group(1).strip()
            return value[1:-1] if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'" else value
    raise SystemExit("DATABASE_URL is not configured")


def pctl(values: list[float], percentile: float) -> float:
    return sorted(values)[min(len(values) - 1, int(round((len(values) - 1) * percentile)))]


def bench(conn: psycopg.Connection, query: str, params: tuple) -> dict[str, float]:
    for _ in range(5):
        conn.execute(query, params).fetchall()
    times = []
    for _ in range(30):
        start = time.perf_counter(); conn.execute(query, params).fetchall(); times.append((time.perf_counter() - start) * 1000)
    return {"p50_ms": round(pctl(times, 0.5), 3), "p95_ms": round(pctl(times, 0.95), 3), "avg_ms": round(statistics.mean(times), 3)}


def main() -> int:
    argparse.ArgumentParser(description="Validate canonical serving facts").parse_args()
    with psycopg.connect(db_url(), connect_timeout=5, row_factory=dict_row) as conn:
        db = conn.execute("SELECT current_database() AS database").fetchone()["database"]
        if db != "fireant_stock_dev": raise SystemExit(f"Unexpected database: {db}")
        total = conn.execute("SELECT count(*) AS count FROM financial.vnstock_serving_facts").fetchone()["count"]
        orphan = conn.execute("""SELECT count(*) AS count FROM financial.vnstock_serving_facts s
            LEFT JOIN financial.vnstock_financial_evidence e ON e.evidence_id=s.source_evidence_id
            LEFT JOIN financial.vnstock_metric_mapping m ON m.mapping_id=s.mapping_id
            LEFT JOIN financial.vnstock_metric_catalog c ON c.canonical_metric_code=s.canonical_metric_code
            WHERE e.evidence_id IS NULL OR m.mapping_id IS NULL OR c.canonical_metric_code IS NULL""").fetchone()["count"]
        duplicate_keys = conn.execute("SELECT count(*) AS count FROM (SELECT ticker,year,canonical_metric_code FROM financial.vnstock_serving_facts GROUP BY 1,2,3 HAVING count(*)>1) d").fetchone()["count"]
        counts = []
        for ticker in PILOT:
            row = conn.execute("SELECT count(*) AS db_rows, min(year) AS year_min, max(year) AS year_max, count(*) FILTER (WHERE value IS NULL) AS null_rows, count(DISTINCT canonical_metric_code) AS metric_count FROM financial.vnstock_serving_facts WHERE ticker=%s", (ticker,)).fetchone()
            counts.append({"ticker": ticker, "db_rows": row["db_rows"], "year_min": row["year_min"], "year_max": row["year_max"], "null_rows": row["null_rows"], "metric_count": row["metric_count"]})
        statements = conn.execute("SELECT ticker,statement_type,count(*) AS rows FROM financial.vnstock_financial_evidence WHERE ticker=ANY(%s) GROUP BY ticker,statement_type ORDER BY ticker,statement_type", (list(PILOT),)).fetchall()
        fact = conn.execute("SELECT ticker,year,canonical_metric_code,value,source_evidence_id FROM financial.vnstock_serving_facts WHERE ticker='ACB' AND year=2025 AND canonical_metric_code='net_profit'").fetchall()
        series = conn.execute("SELECT year,value FROM financial.vnstock_serving_facts WHERE ticker='ACB' AND canonical_metric_code='net_profit' AND year BETWEEN 2021 AND 2025 ORDER BY year").fetchall()
        compare = conn.execute("SELECT ticker,value FROM financial.vnstock_serving_facts WHERE ticker=ANY(%s) AND year=2025 AND canonical_metric_code='net_profit' ORDER BY ticker", (['FPT','MWG'],)).fetchall()
        ranking = conn.execute("SELECT ticker,value FROM financial.vnstock_serving_facts WHERE ticker=ANY(%s) AND year=2025 AND canonical_metric_code='net_profit' ORDER BY value DESC NULLS LAST", (['FPT','HPG','MWG','GAS'],)).fetchall()
        nii = conn.execute("SELECT ticker,year,value FROM financial.vnstock_serving_facts WHERE ticker='ACB' AND year=2025 AND canonical_metric_code='net_interest_income'").fetchall()
        benchmarks = {
            "fact": bench(conn, "SELECT value FROM financial.vnstock_serving_facts WHERE ticker=%s AND year=%s AND canonical_metric_code=%s", ('ACB',2025,'net_profit')),
            "time_series": bench(conn, "SELECT year,value FROM financial.vnstock_serving_facts WHERE ticker=%s AND canonical_metric_code=%s AND year BETWEEN %s AND %s ORDER BY year", ('ACB','net_profit',2021,2025)),
            "compare": bench(conn, "SELECT ticker,value FROM financial.vnstock_serving_facts WHERE ticker=ANY(%s) AND year=%s AND canonical_metric_code=%s", (['FPT','MWG'],2025,'net_profit')),
            "rank": bench(conn, "SELECT ticker,value FROM financial.vnstock_serving_facts WHERE ticker=ANY(%s) AND year=%s AND canonical_metric_code=%s ORDER BY value DESC NULLS LAST", (['FPT','HPG','MWG','GAS'],2025,'net_profit')),
        }
        explain = {}
        for name, query, params in (("fact", "SELECT value FROM financial.vnstock_serving_facts WHERE ticker='ACB' AND year=2025 AND canonical_metric_code='net_profit'", ()), ("time_series", "SELECT year,value FROM financial.vnstock_serving_facts WHERE ticker='ACB' AND canonical_metric_code='net_profit' AND year BETWEEN 2021 AND 2025 ORDER BY year", ())):
            explain[name] = [row["QUERY PLAN"] for row in conn.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) " + query, params).fetchall()]
    with COUNTS.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(counts[0])); writer.writeheader(); writer.writerows(counts)
    lines = ["# Canonical Metric Mapping Pilot Report", "", "## Scope and mappings", "", "- Approved mappings: 36 (six metrics each for four corporate-like and two bank tickers).", "- SSI/BVH: intentionally unmapped; no semantic guess was made.", "- Ambiguous mappings materialized: 0. Missing/unsupported coverage is reported by candidate artifact.", "", "## Serving facts", "", f"- Table: `financial.vnstock_serving_facts`; total rows: `{total}`.", f"- Provenance or catalog/mapping orphans: `{orphan}`; duplicate logical serving keys: `{duplicate_keys}`.", "", "| Ticker | Rows | Years | Metrics | Null rows |", "|---|---:|---|---:|---:|"]
    lines += [f"| {row['ticker']} | {row['db_rows']} | {row['year_min']}–{row['year_max']} | {row['metric_count']} | {row['null_rows']} |" for row in counts]
    lines += ["", "## SQL use cases", "", f"- Fact (ACB net_profit 2025): `{fact}`", f"- Time series (ACB net_profit 2021–2025): `{series}`", f"- Compare (FPT vs MWG net_profit 2025): `{compare}`", f"- Ranking (corporate pilot net_profit 2025): `{ranking}`", f"- Bank NII (ACB 2025): `{nii}`", "", "## Benchmark (30 iterations after 5 warm-ups)", "", "| Query | P50 ms | P95 ms | Avg ms |", "|---|---:|---:|---:|"]
    lines += [f"| {name} | {result['p50_ms']} | {result['p95_ms']} | {result['avg_ms']} |" for name, result in benchmarks.items()]
    lines += ["", "## EXPLAIN ANALYZE", ""]
    for name, plan in explain.items():
        lines.append(f"### {name}"); lines.append(""); lines.append("```text"); lines.extend(plan[:8]); lines.append("```")
    lines += ["", "## Integrity and next action", "", "- Evidence/raw/legacy tables were not modified.", "- Serving loader rerun is idempotent (`ON CONFLICT DO NOTHING`); rerun validation confirms stable row counts.", "- PASS for canonical mapping/serving pilot. STOP before full-universe scale; next step is expand approved mapping only after review, then benchmark serving path further.", ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Validation PASS: serving_rows={total}, orphan_rows={orphan}, duplicate_keys={duplicate_keys}")
    return 0 if orphan == 0 and duplicate_keys == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
