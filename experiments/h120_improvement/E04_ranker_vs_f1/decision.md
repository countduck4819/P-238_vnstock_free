# E04 decision — stock-only ranker vs F1 classifier

The default stock-only XGBRanker and F1 classifier were evaluated across seeds 238–242 with the same five annual folds.

- Ranker mean P@10: `0.3851` (seed SD `0.0092`).
- F1 classifier mean P@10: `0.3349`.
- Mean paired delta: `+0.0502` (seed SD `0.0242`); all five all-fold deltas are positive.

This is not a promotion result. On the latest historical fold (2024), ranker-minus-F1 deltas are `[-0.0385, -0.0308, +0.0538, +0.1885, -0.0269]`: only two of five seeds are positive. The earlier E08 tuned-ranker outer test also failed the lower-95%-CI promotion gate. Do not refit, shadow, or trade this ranker; a new configuration must be selected without reusing the already-inspected 2024 outer outcome and then evaluated on a registered future holdout.
