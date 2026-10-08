"""Shared launcher for isolated V6 candidate-model benchmark runs."""

from __future__ import annotations

import sys

import train_v6_original_shadow as pipeline


LOCAL_DEFAULTS = {
    "--data-dir": "data/vnstock/v6_snapshot",
    "--market-path": "data/vnstock/v6_snapshot/market/VNINDEX.csv",
    "--industry-path": "data/vnstock/v6_snapshot/industry_map.csv",
    "--market-cap-path": "data/vnstock/v6_snapshot/symbols.csv",
}


def run_candidate(
    candidate: str,
    models: tuple[str, ...],
    default_trials: int,
    default_device: str = "cpu",
) -> None:
    """Run only ``models`` while preserving the V6 data/evaluation protocol."""
    provided = list(sys.argv[1:])
    defaults: list[str] = []
    if "--allow-stale-cache" not in provided:
        defaults.append("--allow-stale-cache")
    for option, value in LOCAL_DEFAULTS.items():
        if option not in provided:
            defaults.extend((option, value))
    if "--models-dir" not in provided:
        defaults.extend(("--models-dir", f"models/wave_ignition/v6_model_benchmark/{candidate}"))
    if "--reports-dir" not in provided:
        defaults.extend(("--reports-dir", f"eval/runs/v6_model_benchmark/{candidate}"))
    if "--trials" not in provided:
        defaults.extend(("--trials", str(default_trials)))
    if "--compute-device" not in provided:
        defaults.extend(("--compute-device", default_device))
    pipeline.MODEL_NAMES = models
    sys.argv = [sys.argv[0], *defaults, *provided]
    pipeline.main()
