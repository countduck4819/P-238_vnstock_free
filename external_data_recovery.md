# External Financial Data Recovery Agent

`ExternalFinancialDataRecoveryAgent` handles explicitly missing evidence. It
searches only through an injected search client, ranks identified sources and
returns evidence with provenance metadata. It never writes PostgreSQL and each
result is marked `numerical_truth: false`.

Source ranking:

1. `TIER_1`: annual/audited reports, company announcements, exchange filings,
   and identified official domains.
2. `TIER_2`: configured reliable financial databases.
3. `TIER_3`: other identified financial-news sources.

Results without an HTTP(S) URL, title, publisher, or explicit `value` /
`claim_value` are rejected. Search failures are retried within bounded
`max_retries` and `timeout_seconds`; no value is inferred from prose.

The LangGraph node `recover_external_data` runs only when an availability
report has missing evidence and web research is configured. It stores results
in `external_recovery_evidence`, separate from PostgreSQL evidence.
