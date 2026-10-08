# Phase C — H120 ranker generation v2

This directory is intentionally empty of metrics until the pinned dataset
snapshot is rehydrated. Historical E04/E08 outputs must not be copied here:
they include the already-inspected 2024 fold and are not valid configuration
selection evidence for this generation.

Required sequence:

1. R1: run the locked baseline ranker on `fold_2020`–`fold_2023`.
2. R2: repeat exactly those folds for seeds 238–242, then run
   `scripts/aggregate_h120_ranker_phase_c.py`.
3. R3: use the locked random search on exactly those inner folds; write all
   trial artifacts before selecting a configuration.
4. Freeze the selected config and its checksums before the registered future
   holdout is ever opened.

No refit, shadow run, or trade authorization is granted by this directory.
