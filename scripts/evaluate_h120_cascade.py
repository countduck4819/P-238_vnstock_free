"""Evaluate a frozen cascade meta-model on a supplied OOF/final table."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.wave_cascade import add_strength_ranking_score, cascade_metrics
from src.training.xgboost_pipeline import SigmoidCalibration


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frame", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--calibration", type=Path)
    parser.add_argument("--target-column", default="y_cont_h120")
    parser.add_argument("--threshold", type=float, required=True)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--candidate-column", default="p_h120")
    parser.add_argument("--candidate-k", type=int, default=50)
    parser.add_argument("--candidate-mode", choices=("universe", "pool"), default="universe")
    parser.add_argument("--strength-columns", default="")
    parser.add_argument("--strength-weight", type=float, default=0.0)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    frame = pd.read_parquet(args.frame)
    model = joblib.load(args.model)
    frame = frame.copy()
    frame["p_cascade"] = model.predict_proba(frame)
    probability_column = "p_cascade"
    if args.calibration:
        calibration_payload = json.loads(args.calibration.read_text(encoding="utf-8"))
        calibration = SigmoidCalibration.from_dict(calibration_payload)
        frame["p_cascade_calibrated"] = calibration.predict(frame["p_cascade"])
        probability_column = "p_cascade_calibrated"
    ranking_column = probability_column
    strength_columns = tuple(
        column.strip() for column in args.strength_columns.split(",") if column.strip()
    )
    if strength_columns and args.strength_weight > 0.0:
        frame = add_strength_ranking_score(
            frame,
            probability_column=probability_column,
            strength_columns=strength_columns,
            strength_weight=args.strength_weight,
        )
        ranking_column = "p_rank"
    metrics = cascade_metrics(
        frame,
        probability_column=probability_column,
        target_column=args.target_column,
        threshold=args.threshold,
        top_k=args.top_k,
        candidate_probability_column=(
            args.candidate_column if args.candidate_mode == "pool" else None
        ),
        candidate_k=args.candidate_k,
        ranking_probability_column=ranking_column,
    )
    payload = json.dumps(metrics, indent=2, ensure_ascii=False, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
