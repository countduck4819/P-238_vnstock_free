# E03 decision — feature groups, W0 fixed

All models use the same five annual folds, V3 target validation, W0, seed 238, and exact daily Top-10 evaluation.

| Group | Features | P@10 | Delta vs F0 | 95% CI of delta |
|---|---:|---:|---:|---|
| F0 full_83 | 83 | 0.2823 | — | — |
| F1 stock_primitives | 50 | 0.3308 | +0.0485 | [+0.0162, +0.0808] |
| F2 no_composites | 76 | 0.2892 | +0.0069 | [-0.0154, +0.0308] |
| F3 deduplicated | 77 | 0.2685 | -0.0138 | [-0.0346, +0.0069] |

F1 is the only group that passes the pre-specified positive-CI evidence criterion. Its five-seed confirmation has mean P@10 `0.3349` versus F0 `0.2902`; mean paired delta `+0.0448` (SD `0.0224`), positive in all five seeds. F1 is the research feature policy for subsequent model work. This does not close the external corporate-action or industry lineage gates.

Status: research-only; not trade-authorized.
