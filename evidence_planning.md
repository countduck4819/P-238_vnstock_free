# Evidence Planning Skill

`EvidencePlanningSkill` consumes a validated `FinancialAnalysisBlueprint` and
answers only: “what evidence should be collected?” It performs no database,
Qdrant, web, or calculation calls.

The output contract is `EvidencePlan` in
`src/services/evidence_planning.py`:

```json
{
  "objective": "Collect evidence for FINANCIAL_HEALTH_ANALYSIS of FPT",
  "evidence_items": [
    {
      "name": "revenue_growth",
      "category": "DERIVED_METRIC",
      "priority": "HIGH",
      "source_preference": ["CALCULATION_ENGINE"],
      "fallback_source": ["POSTGRES"],
      "required": true
    }
  ]
}
```

The ontology mapping is deliberately closed:

- numeric facts → `POSTGRES`;
- derived metrics → `CALCULATION_ENGINE`, then `POSTGRES`;
- qualitative knowledge → `QDRANT`, then `WEB`;
- external events → `WEB`, then `QDRANT`.

The `plan_evidence` LangGraph node stores the plan in `evidence_plan` and
emits a structured log and trace event. Unit tests are in
`tests/test_api/test_evidence_planning.py`.
