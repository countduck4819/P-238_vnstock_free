# E08 decision — tuned stock-only ranker, outer fold 2024

Status: **no-go for E09 refit and shadow**. This is research evidence only and is not trade-authorized.

## Frozen protocol

- Inner selection: four random trials over `fold_2020`–`fold_2023`.
- The selected configuration was frozen in `h120_ranker_stock_primitives_e08_outer2024_v1.yaml` before outer scoring.
- Outer evaluation: `fold_2024`, 26 paired daily observations, same-date Top-10 comparison with the frozen H120 classifier champion.
- Confirmation: seeds `238`–`242`; only the random seed changed.
- Git commit at run time: `a7ab6ca914f410bfe22ba2346e2e21ae44605492` with a dirty worktree.
- Frozen config SHA-256: `91845E9D73983E047E28EBD43307B975A928C6CEC739F8EBD36C5B7B127F38FD`.

## Results

Champion outer P@10 is `0.4308`. Challenger P@10 is `0.4554` on average across five seeds (sample SD `0.0167`), for mean paired delta `+0.0246`.

| Seed | Challenger P@10 | Paired delta P@10 | 95% bootstrap CI |
|---:|---:|---:|---|
| 238 | 0.4808 | +0.0500 | [0.0000, 0.0962] |
| 239 | 0.4538 | +0.0231 | [-0.0500, 0.0885] |
| 240 | 0.4346 | +0.0038 | [-0.0769, 0.0769] |
| 241 | 0.4500 | +0.0192 | [-0.0308, 0.0731] |
| 242 | 0.4577 | +0.0269 | [-0.0347, 0.0885] |

## Gate decision

The stop rule is not triggered: no confidence interval lies wholly below zero. However, the promotion gate is not met: no seed has a lower 95% confidence bound strictly above zero, and the outer gain is materially seed-sensitive. Do not refit E09, deploy, or start shadow monitoring from this candidate.

Next valid work is to address the unresolved W0/W1 and F0–F3 prerequisites in a new experiment generation, then register a fresh future holdout before any new promotion attempt.
