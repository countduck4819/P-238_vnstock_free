# Data Availability Analyzer

`DataAvailabilityAnalyzer` resolves an `EvidencePlan` against static
capability registries. It does not connect to PostgreSQL, Qdrant, external
research, or an LLM, so “available” means the source/metric is supported by
the current serving ontology—not that a particular company/year row exists.

## Output

```json
{
  "available": [{"evidence": "profit", "category": "NUMERIC_FACT", "source": "POSTGRES"}],
  "missing": [],
  "derivable": [{
    "metric": "roe",
    "formula": "net_income / average_equity",
    "dependencies": ["net_profit", "total_equity"]
  }],
  "external_required": []
}
```

The registries are extensible through `MetricRegistry.register` and
`EvidenceRegistry.register`. The LangGraph node `analyze_availability` stores
the report in `state["data_availability"]` and emits a structured trace/log.
Missing evidence remains explicitly missing; it is never replaced with zero.
