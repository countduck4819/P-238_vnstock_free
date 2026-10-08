# Derived Metric Engine

`DerivedMetricEngine` in `src/services/derived_metrics.py` computes a closed
set of deterministic metrics from caller-supplied raw facts. It performs no
LLM calls, database writes, or persistence.

Supported metrics:

`revenue_growth`, `profit_growth`, `gross_margin`, `operating_margin`,
`net_margin`, `ROA`, `ROE`, and `debt_ratio`.

Example:

```python
from src.services.derived_metrics import calculate_metric

calculate_metric("ROE", {"net_income": 12000, "equity": 50000})
# {"metric": "ROE", "value": 0.24,
#  "formula": "net_income / equity", "confidence": "HIGH"}
```

Missing facts raise `MissingFactError`; a zero denominator raises
`ZeroDenominatorError`. Neither condition is converted to a fabricated zero.
New formulas can be registered through `MetricRegistry.register`.
