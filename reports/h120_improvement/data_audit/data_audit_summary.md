# H120 Phase-1 data lineage audit

## Mechanical quality

- Processed stock rows: 1,800,494; excluded rows: 2,980.
- Invalid OHLCV reasons after cleaning: 0.
- Missing sessions are audit-only and not imputed: 948,708.
- Missing-session enrichment uses prior turnover and observation-span proxies only; it cannot label suspension/delisting without an external listing-status source.

## Selection funnel

- Feature-ready rows reported by feature audit: 925,494 / 1,800,494 (51.40%).
- Labeled H120 rows: 165,875; symbols: 840.
- Per-year funnel and unavailable reasons are in `universe_funnel_by_year.csv` and `feature_ready_selection_bias.csv`.

## Corporate actions and industry lineage

- Price policy is `adjusted`. Flagged jump/cooldown rows are exported to `corporate_action_audit.parquet`.
- Internal source policy, timestamps and SHA-256 checksums are in `source_lineage.json`.
- No external, point-in-time split/dividend/rights event source is present in this snapshot. Corporate-action verification remains **lineage_risk_open**.
- Industry map is a static current ICB snapshot with no effective-date column. Sector features remain **lineage_risk_open** and are excluded from the first stock-only challenger.

## Decision

Mechanical data quality is sufficient for research. Production lineage is not fully closed until an external point-in-time corporate-action and industry-history source is recorded.
