# E02 decision — W0 vs W1

W0 (unit base weight) reproduces the frozen baseline exactly: raw OOF P@10 `0.2823` across 130 paired dates. W1 uses only V3 event-uniqueness weight (ESS `127,887 / 165,875`), keeps the identical target, and produces raw P@10 `0.2954`.

The W1 paired delta is `+0.0131`, with 95% date-bootstrap CI `[-0.0100, +0.0377]`; MAP@10 changes by `-0.0034`. The confidence interval crosses zero, so W1 is not promoted. F0–F3 retain W0 as the locked control.

Status: research-only; not trade-authorized.
