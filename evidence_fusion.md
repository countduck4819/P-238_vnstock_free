# Evidence Fusion Node

`EvidenceFusionNode` combines PostgreSQL facts, derived calculations, Qdrant
qualitative records and external financial evidence into one
`EvidencePackage`. It is deterministic and does not call an LLM.

Priority order:

1. PostgreSQL numerical truth
2. Derived calculation
3. External financial source
4. Qdrant qualitative knowledge

When different numeric candidates share the same metric/year, the highest
priority candidate is exposed in `facts`, but every candidate is retained in
`conflicts` and `conflict` is set to `true`. A limitation is added so the
disagreement cannot be mistaken for a silently resolved value.

The LangGraph node is `fuse_evidence`; its result is stored in
`state["evidence_package"]`. Qdrant text is kept in `interpretations`, while
external and derived provenance remains attached to each fact.
