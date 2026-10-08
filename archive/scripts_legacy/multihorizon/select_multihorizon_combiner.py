"""Choose legacy-intersection or missing-aware combiner using causal OOF only."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.multihorizon_final import compare_causal_oof_combiners  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy-run", type=Path, required=True)
    parser.add_argument("--candidate-run", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/experiments/wave_multihorizon_final_v1.yaml")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def load_threshold(run: Path) -> float:
    manifest_path = run / "model_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    threshold = manifest.get("deployment_threshold")
    if threshold is None:
        metrics = json.loads((run / "audit" / "oof_metrics.json").read_text(encoding="utf-8"))
        threshold = metrics.get("deployment_threshold_from_causal_oof")
    if threshold is None:
        raise ValueError(f"No OOF-frozen threshold for {run}")
    return float(threshold)


def normalize_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): normalize_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize_json(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if not np.isfinite(value) else float(value)
    return value


def main() -> None:
    args = parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    selection = config["oof_candidate_selection"]
    legacy = pd.read_parquet(args.legacy_run / "predictions" / "oof_predictions.parquet")
    candidate = pd.read_parquet(args.candidate_run / "predictions" / "oof_predictions.parquet")
    report = compare_causal_oof_combiners(
        legacy,
        candidate,
        legacy_threshold=load_threshold(args.legacy_run),
        candidate_threshold=load_threshold(args.candidate_run),
        top_k=int(config["ranking"]["top_k"]),
    )
    delta = report["delta_candidate_minus_legacy"]
    checks = {
        "average_precision": delta["average_precision"] >= selection["minimum_average_precision_delta"],
        "top_k_precision": delta["top_k_event_weighted_precision"] >= selection["minimum_top_k_precision_delta"],
        "brier_score": delta["brier_score"] <= selection["maximum_brier_score_delta"],
        "scored_coverage": report["candidate_scored_rows"] >= report["legacy_scored_rows"],
    }
    chosen = "missing_aware_candidate" if all(checks.values()) else "legacy_intersection"
    output = {
        **report,
        "selection_scope": "causal_oof_only",
        "final_test_used_for_selection": False,
        "checks": checks,
        "chosen_policy": chosen,
        "chosen_run": str((args.candidate_run if chosen == "missing_aware_candidate" else args.legacy_run).resolve()),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(normalize_json(output), ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(normalize_json(output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
