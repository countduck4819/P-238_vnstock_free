# Benchmark Engine

`BenchmarkAnalyzer` compares source-backed company metrics against benchmarks
registered in `BenchmarkRegistry`. It does not fetch, invent or modify
financial truth.

Register only sourced values:

```python
registry.register_benchmark(
    "roe", "FPT", 0.18, "HISTORICAL",
    source="annual-report-2023",
    evidence_refs=["hist:roe:2023"],
    year=2023,
)
```

Historical, peer and industry entries are resolved through
`BenchmarkResolver`. Missing registry entries produce `UNKNOWN`; multiple
different values for the same metric/type produce `UNKNOWN` and a limitation.
The LangGraph node `benchmark_analysis` stores the result in
`state["benchmark_result"]` and never emits a trading recommendation.
