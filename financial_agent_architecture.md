# FinSight Financial Agent Architecture

FinSight now exposes one supervisor boundary while retaining a small number of
purposeful graph nodes. A user does not select an analysis type.

```text
User question
  -> FinancialAgentSupervisor / UnifiedFinancialQueryHandler
  -> deterministic router or bounded LangGraph supervisor
  -> question understanding
  -> evidence planning + availability
  -> registered tool actions
  -> observations / evidence fusion
  -> financial reasoning, interpretation, benchmark, risk review
  -> analyst report / safe answer
```

## Components

- `FinancialAgentSupervisor` (`src/services/financial_supervisor.py`) is the
  public unified handler. Simple fact/rank/compare requests use the existing
  deterministic query pipeline; analytical or multi-step questions use
  `FinancialResearchAgent` and its LangGraph.
- `TOOL_REGISTRY` (`src/services/agent_actions.py`) is the single action-to-tool
  registry. `QueryHarness.check_availability` validates registration before
  execution.
- `EvidencePlanningSkill`, `DataAvailabilityResolver`, and the graph's
  evidence-plan mapper choose required sources without fetching data.
- `QueryHarness`/`QueryTools` provide PostgreSQL numerical facts, derived
  metrics, and Qdrant qualitative retrieval. `ControlledWebResearch` is the
  source-ranked external fallback.
- `EvidenceFusionNode` preserves provenance and conflicts. Reasoning and all
  later engines only consume the resulting evidence package.

## Failure behavior

Tool failures remain in internal `results` and `agent_trace` for debugging, but
the public composer maps them to a Vietnamese unknown/limited-data message and
never exposes `TOOL_UNAVAILABLE`, connection strings, or exception details. A
Qdrant failure can use controlled external research when configured; if no
fallback is available, the answer is explicitly UNKNOWN rather than an invented
number.

## Scope and limitations

The agent is evidence-bounded, not omniscient: an unseen metric or missing year
is reported as unavailable. It does not promise price movements or issue
buy/sell recommendations. Database, Qdrant, model and external-search
availability are deployment concerns; the supervisor can only reason over the
evidence returned by those tools.
