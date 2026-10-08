# Phase C/D rerun summary

Dataset: `wave_dataset_continuation_h120_v3`, run `20260824T114000Z`.
The rebuilt dataset has 165,875 feature-ready labeled rows for 840 symbols and
uses only `wave_continuation_h120_v3_eventweights`.

- R2 (seeds 238–242): mean daily P@10 `0.3731`, seed SD `0.0057`, worst-fold
  lift `1.3417`.
- R3 selected trial 14: daily P@10 `0.3923`; paired delta versus the frozen
  champion is `+0.1471`, bootstrap 95% CI `[+0.1019, +0.1914]`; worst-fold
  lift is `1.5105`.
- Phase D: C2 regime-intercept has the lowest mean Brier (`0.1621`), log loss
  (`0.6918`), and ECE (`0.1465`) among C0–C2. It remains an output for
  risk/monitoring only and does not change `rank_score` ordering.

Phase E is not authorized until the pending selection record is explicitly
reviewed and frozen. Phase F remains sealed until the registered future period
has accrued 120 trading sessions and the one-time outcome-opening gate is met.
