# GEMINI.md — ADLC entrypoint

This file exists so Gemini CLI finds the agent contract. `.ADLC.md` is the single source of truth; the other agent entrypoints in this repository carry this same text under the filename each tool looks for.

`.ADLC.md` is the canonical lifecycle, quality, security, work-tracking, and handoff policy for this repository; follow it before acting.

It is read by section, not whole: `adlc rules` lists the sections with their sizes, `adlc rules <topic>` prints the ones a task needs verbatim (~300-1,400 tokens each) instead of the ~11k-token document, and `adlc rules --all` is there for the rare task that really is the whole policy.

Resolve project-specific facts only through the context adapters required by `.ADLC.md` (normally `.project-contexts/`). Do not infer a project's board, branches, commands, APIs, data boundaries, or owners from this file or from another workspace.

Route by the lightest risk class that fits: `micro` (docs/metadata) → `code_change` (bugfix/refactor with no contract change) → `feature_change` → `critical_change`. Read-only questions, explanations and code-reading reviews are answered directly — no ticket, no workflow run, no heavy skill. This does not cover a request to review an actual MR/PR: that always routes to ADLC's own `/review` skill. Run `adlc asset-path .agents/skills/review/SKILL.md` to locate and read it directly, not via the Claude Code `Skill` tool.

To see why a request routes to a given workflow and skill set:

```bash
adlc workflow compose --request "<task>" --json
```

Operational detail lives in the installed ADLC runtime's `references/`. Run `adlc asset-path .agents/references/<name>` to locate a file when the task actually reaches it, not upfront. Any `.agents/...` path in ADLC policy or skills denotes a runtime asset; resolve it with `adlc asset-path` before use instead of assuming a project-local `.agents/`.

For cross-repo questions — which service consumes an endpoint, what a change impacts across services, which endpoints no test touches — query the pre-computed Lifecycle Graph before searching by hand: `adlc graph query "<question>"` (MCP: `adlc_graph_query`, `adlc_graph_pack`); build it once per checkout with `adlc graph build`. It describes AS-IS state with per-edge confidence — `inferred` edges are never delivery evidence.
