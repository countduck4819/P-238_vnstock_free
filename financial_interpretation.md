# Financial Interpretation Engine

`FinancialInterpretationEngine` consumes only `FinancialAnalysisResult` and
turns existing FACT/INFERENCE statements into conservative financial signals.
It does not fetch data, parse external sources, calculate new values or issue
trading recommendations.

Signals use the closed categories `GROWTH`, `PROFITABILITY`, `EFFICIENCY`,
`LEVERAGE`, `CASHFLOW`, and `BUSINESS_QUALITY`, with directions
`POSITIVE`, `NEGATIVE`, `NEUTRAL`, or `UNKNOWN`. Any non-unknown signal must
carry `evidence_refs`; unsupported or insufficient evidence produces UNKNOWN.

The LangGraph node `financial_interpretation` stores its output in
`state["financial_signals"]` between `financial_reasoning` and `synthesize`.
