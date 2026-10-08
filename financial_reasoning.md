# Financial Reasoning Engine

`FinancialReasoningEngine` consumes only an `EvidencePackage`. It does not
query PostgreSQL, Qdrant or web sources. The output is a strict
`FinancialAnalysisResult` with Executive Summary, Financial Trend,
Profitability Analysis, Business Quality, Strengths, Risks, Unknowns and a
0–100 confidence score.

Statements are explicitly typed as `FACT`, `INFERENCE`, `UNKNOWN` or `RISK`.
FACT/INFERENCE/RISK statements must carry `evidence_refs`; unknowns are used
when the package has insufficient evidence. Conflict references are preserved
as `conflict:<metric>:<year>`.

Confidence is calculated deterministically from available versus limited
evidence. Conflicts cap the score at 69. The engine never creates or modifies
financial values.

The LangGraph node `financial_reasoning` runs after the critic and stores the
result in `state["financial_analysis_result"]` before synthesis.
