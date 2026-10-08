# H120 Phase A — closure record

Date: 2026-08-24  
Scope: H120 research program only; this is not production or trade authorization.

## Closed controls

- **H120 purge:** `src/training/splits.py` keeps a training row only when its
  `label_end_date` is earlier than the validation start minus the configured
  five-session embargo.  With a 120-session label this places the last usable
  training decision at least 126 market sessions before validation starts.  The
  H120 regression test is in `tests/test_training/test_splits.py`.
- **Sector:** the resolved `stock_primitives` group excludes market, sector,
  sector-relative and corporate-action features.  The sector-relative group is
  explicitly blocked by the static-current ICB lineage gate.  The invariant is
  tested in `tests/test_training/test_h120_feature_groups.py`.
- **Corporate action:** no point-in-time split/dividend/rights source is present
  in this workspace.  The enforced exception is to exclude
  `corporate_action_jump` and `corporate_action_recent` from the first ranker,
  and to prohibit a production candidate from claiming that adjusted-price
  lineage is closed.

## Selection-bias audit contract

The raw snapshot required for a fresh row-level audit is not present locally.
No new coverage figure is asserted here.  The historical plan records 925,494
feature-ready rows, 875,000 unavailable rows, a 51.4% ready rate, and a
universe reduction from 1,512 to 840 symbols.  Those figures must be treated as
historical evidence only until regenerated from the pinned snapshot.

`scripts/audit_h120_data_lineage.py` is the required reproducible runner.  Once
the snapshot is restored, it must be run before a promotion attempt and must
write the following under this directory:

- `corporate_action_audit.parquet`
- `missing_session_breakdown.csv`
- `feature_ready_selection_bias.csv`
- `universe_funnel_by_year.csv`
- `industry_lineage_report.json`
- `source_lineage.json`

The runner already records source checksums and timestamps, analyses
feature-ready availability by year, and identifies the remaining external
corporate-action, listing-status, and industry-history gaps.  A missing
point-in-time source remains a production blocker, not a reason to re-enable
the excluded features.

## Phase decision

Phase A is closed for the next **research-only** experiment generation: purge,
feature-policy, and exception controls are explicit and testable.  Production
lineage is still open until the pinned raw snapshot is rehydrated and a
point-in-time corporate-action/industry source is supplied.
