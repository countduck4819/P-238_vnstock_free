# Evidence-Bounded Equity Analysis

`EquityAnalysisNode` consumes an `EvidencePackage` and produces seven
sections: Executive Summary, Financial Trend, Business Quality, Strength,
Risk, Missing Information, and Confidence Score.

Every `FACT` and `INFERENCE` statement includes `evidence_refs`. Missing
evidence is reported as `UNKNOWN`; no numerical value is recalculated,
changed, or invented. Conflicts from fusion remain visible in the Risk
section and are referenced as `conflict:<metric>:<year>`.

The implementation is deterministic and does not call an LLM.
