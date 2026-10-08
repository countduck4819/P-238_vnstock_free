# Risk Review Engine

`RiskReviewEngine` evaluates only the existing
`FinancialAnalysisResult`, `FinancialSignalResult` and `BenchmarkResult`.
It performs no database/web calls and does not alter evidence.

Rules implemented:

- negative high-strength leverage signal → `LEVERAGE/HIGH`;
- positive profitability plus negative cashflow → `EARNINGS_QUALITY`;
- negative growth signal → `GROWTH`;
- industry benchmark position `BELOW` → relative weakness risk.

Every emitted risk requires evidence references. If references or supporting
signals are absent, the condition is placed in `unknown_risks` instead. The
engine never predicts bankruptcy, creates a price target or recommends a
transaction. LangGraph stores the report in `state["risk_review"]`.
