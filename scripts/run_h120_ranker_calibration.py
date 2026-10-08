"""Compare causal C0-C2 probability calibrators on one frozen rank-score artifact."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.training.h120_experiment_protocol import H120ExperimentProtocol  # noqa: E402
from src.training.h120_ranker_calibration import (  # noqa: E402
    causal_ranker_calibration_predictions,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ranker-oof", type=Path, required=True)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/experiments/h120_ranker_calibration_generation_v2.yaml"),
    )
    parser.add_argument(
        "--protocol",
        type=Path,
        default=Path("configs/experiments/h120_ranker_generation_v2.yaml"),
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def mean_calibration_metrics(audit: pd.DataFrame) -> dict[str, float | int]:
    successful = audit.loc[audit["status"].eq("ok")].copy()
    metrics = ["brier_score", "log_loss", "ece", "calibration_slope", "calibration_intercept"]
    return {
        "evaluated_folds": int(len(successful)),
        **{f"mean_{metric}": float(successful[metric].mean()) for metric in metrics},
    }


def main() -> int:
    args = parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    protocol = H120ExperimentProtocol.from_yaml(args.protocol)
    if config["protocol"] != str(args.protocol).replace("\\", "/"):
        raise ValueError("Calibration config must reference the frozen experiment protocol.")
    oof = pd.read_parquet(args.ranker_oof)
    protocol.validate_selection_folds(sorted(str(fold) for fold in oof["fold_id"].unique()))
    inputs = config["input_contract"]
    evaluation = config["evaluation"]
    output = oof.copy()
    candidate_summary: dict[str, dict] = {}
    audit_parts: list[pd.DataFrame] = []
    for candidate_id, candidate in config["calibration_candidates"].items():
        calibrated, audit = causal_ranker_calibration_predictions(
            output,
            method=str(candidate["method"]),
            output_column=str(candidate["output_column"]),
            score_probability_column=str(inputs["score_probability_column"]),
            regime_column=str(inputs["regime_column"]),
            rolling_prior_folds=candidate.get("rolling_prior_folds"),
            clip_epsilon=float(evaluation["clip_epsilon"]),
            random_seed=int(evaluation["random_seed"]),
            ece_bins=int(evaluation["ece_bins"]),
        )
        output[str(candidate["output_column"])] = calibrated[str(candidate["output_column"])]
        audit.insert(0, "candidate_id", candidate_id)
        audit_parts.append(audit)
        candidate_summary[candidate_id] = {
            "method": candidate["method"],
            "output_column": candidate["output_column"],
            **mean_calibration_metrics(audit),
        }
    args.output.mkdir(parents=True, exist_ok=False)
    output.to_parquet(args.output / "calibrated_oof_predictions.parquet", index=False)
    pd.concat(audit_parts, ignore_index=True).to_csv(args.output / "calibration_by_fold.csv", index=False)
    manifest = {
        "status": "research_only_calibration_comparison",
        "protocol": protocol.to_manifest(),
        "ranking_contract": config["ranking_contract"],
        "ranker_oof": str(args.ranker_oof),
        "candidates": candidate_summary,
        "trade_authorized": False,
    }
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
