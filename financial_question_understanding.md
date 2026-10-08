# Financial Question Understanding Skill

The skill converts a natural-language request into a validated,
answer-free `FinancialAnalysisBlueprint`. It does not query PostgreSQL,
Qdrant, web search, or generate financial values.

## Graph placement

`FinancialAgentGraph` runs `understand_question` after the existing `plan`
node and before `validate_action`. This preserves the planner's existing LLM
call order while making the blueprint available in `LangGraphAgentState` as
`financial_blueprint`. The node emits a trace event named
`understand_question` and records whether deterministic fallback was used.

## Schema

The Pydantic models and closed enums are in
`src/services/financial_question_understanding.py`:

- `FinancialQuestionUnderstandingInput`: only `user_query` (1–2000 chars).
- `FinancialAnalysisBlueprint`: the required `intent`, `companies`, `sector`,
  `period`, `analysis_type`, `required_evidence`, and `risk_flags` fields.
- `EvidenceRequirement`: closed evidence names and types; unknown metrics and
  extra fields are rejected.

## Example execution trace

Input: `FPT đang khỏe lên hay yếu đi?`

```json
{
  "node": "understand_question",
  "decision": "DETERMINISTIC_FALLBACK",
  "intent": "FINANCIAL_HEALTH_ANALYSIS",
  "evidence_count": 5
}
```

The corresponding blueprint contains `FPT`, no invented period or numbers,
and evidence requirements such as `revenue_growth`, `profit_growth`,
`net_margin`, and qualitative `business_driver`.

## Tests

`tests/test_api/test_financial_question_understanding.py` covers fact lookup,
financial health, bank ranking, provider failure fallback, rejection of
invented LLM entities/metrics, and strict schema validation.
