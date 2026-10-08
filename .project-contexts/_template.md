# Workspace Context Template

Use this for one stable workspace in a multi-project repository. First register its id/root in `project-context.md`; this file supplies details that cannot safely be shared with another workspace. Fill only facts verified from the target project; leave an item empty or mark it `unknown` rather than copying a value from another repository.

## Identity And Scope

- Context id:
- Root:
- Platform/framework:
- Owner/team:
- In scope:
- Out of scope:
- Upstream/downstream workspaces:
- Contract type: HTTP / event / shared schema / auth / UI client / none

## Sources Of Truth

- Business/BRD:
- Architecture/API/schema:
- Design/Figma (if UI):
- Work tracking keywords (optional): Jira project/key prefix, Confluence space/page hints, board/team names. Keep stable shared defaults in `.project-contexts/work-tracking.json` instead of duplicating them here.
- Security/compliance:
- README/runbook:

## Paths And Commands

- Source/test/config/migration paths:
- Install/restore:
- Focused test:
- Build:
- Lint/format:
- Audit:
- Run locally:
- Healthcheck/smoke (verified fast command proving env + app can run; `unknown` until verified):
- Migration check:

## Contracts And Conventions

- API/event/schema contract and version:
- Actors, auth and ownership/data scope:
- PII/regulated-data boundary:
- Logging/error/copy language:
- Persistence/migration policy:
- UI states/accessibility (if UI):
- Required test cases:

## Dependencies And Verification

- Provider workspaces and contracts consumed:
- Consumer workspaces and contracts exposed:
- Change impact trigger: what requires multi-workspace verification?
- Per-workspace verification command:
- Integration proof command or reason it cannot run:

## Work Tracking Discovery

- Existing Jira/Confluence anchors:
- TWG discovery commands to verify context:
- GitFlow source page or branch policy:
- Board/sprint selection notes:
- When to update `.project-contexts/work-tracking.json`:

## Skill Adapters

- `/ba`: source docs or `python3 .agents/skills/ba/scripts/ba_brd_analyzer.py ...`
- `/qc`: focused test command/generator:
- `/dev`: codegen or local pattern path:
- `/devops`: `bash .agents/skills/devops/scripts/devops_pipeline.sh ...` when risk requires it
- `/sec` and `/release`: workspace-specific gates:

## Completion Evidence

- `primary_workspace` and `affected_workspaces`:
- Files changed by workspace:
- Tests/build by workspace:
- Contract/integration proof:
- Residual risk:
