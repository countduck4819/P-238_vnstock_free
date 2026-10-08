"""Backtest a frozen cascade final population with transaction costs."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.backtest import BacktestConfig, run_backtest  # noqa: E402
from src.evaluation.wave_model import EvaluationConfig  # noqa: E402
from src.training.xgboost_pipeline import SigmoidCalibration  # noqa: E402


def normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def stock_data(
    directory: Path,
    symbols: set[str],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for symbol in sorted(symbols):
        path = directory / f"{symbol}.csv"
        if not path.is_file():
            continue
        frame = pd.read_csv(path, parse_dates=["date"])
        frame = frame.loc[frame["date"].between(start, end)]
        if not frame.empty:
            frames.append(frame)
    if not frames:
        raise RuntimeError("No OHLCV data available for cascade final predictions.")
    return pd.concat(frames, ignore_index=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frame", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--label-manifest", type=Path, required=True)
    parser.add_argument("--evaluation-config", type=Path, default=Path("configs/wave_ignition_evaluation_v1.yaml"))
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--max-positions", type=int, default=3)
    parser.add_argument("--holding-sessions", type=int, default=120)
    parser.add_argument("--score-column", default="p_cascade_calibrated")
    parser.add_argument("--output-root", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.top_k <= 0 or args.max_positions <= 0 or args.holding_sessions <= 0:
        raise ValueError("top-k, max-positions, and holding-sessions must be positive.")
    predictions = pd.read_parquet(args.frame).copy()
    predictions["date"] = pd.to_datetime(predictions["date"], errors="raise")
    model = joblib.load(args.model)
    predictions["p_cascade"] = model.predict_proba(predictions)
    calibration = SigmoidCalibration.from_dict(
        json.loads(args.calibration.read_text(encoding="utf-8"))
    )
    predictions["p_cascade_calibrated"] = calibration.predict(predictions["p_cascade"])
    required = {"symbol", "date", args.score_column}
    missing = sorted(required - set(predictions.columns))
    if missing:
        raise RuntimeError(f"Final cascade frame is missing {missing}")
    predictions["p_entry_calibrated_temporal"] = predictions[args.score_column]
    predictions["p_strength"] = 0.0

    label_manifest = json.loads(args.label_manifest.read_text(encoding="utf-8"))
    data_sources = label_manifest["data_sources"]
    vnindex = pd.read_csv(data_sources["vnindex_ohlcv"], parse_dates=["date"])
    evaluation = EvaluationConfig.from_yaml(args.evaluation_config)
    base_config = BacktestConfig.from_dict(evaluation.backtest)
    config = replace(
        base_config,
        top_k_per_day=args.top_k,
        max_positions=args.max_positions,
        maximum_holding_sessions=args.holding_sessions,
        score_column=args.score_column,
    )
    end = min(
        vnindex["date"].max(),
        predictions["date"].max() + pd.Timedelta(days=args.holding_sessions * 3),
    )
    stock = stock_data(
        Path(data_sources["stock_ohlcv"]),
        set(predictions["symbol"].astype(str)),
        predictions["date"].min(),
        end,
    )
    output = args.output_root / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    output.mkdir(parents=True, exist_ok=False)
    metrics, equity, trades, skipped, yearly = run_backtest(predictions, stock, vnindex, config)
    (output / "equity_curve.parquet").parent.mkdir(parents=True, exist_ok=True)
    equity.to_parquet(output / "equity_curve.parquet", index=False)
    trades.to_parquet(output / "trades.parquet", index=False)
    skipped.to_parquet(output / "skipped_signals.parquet", index=False)
    yearly.to_csv(output / "yearly_metrics.csv", index=False)
    payload = {
        "frame": str(args.frame.resolve()),
        "label_manifest": str(args.label_manifest.resolve()),
        "score_column": args.score_column,
        "top_k": args.top_k,
        "max_positions": args.max_positions,
        "holding_sessions": args.holding_sessions,
        "metrics": metrics,
        "config": config.__dict__,
    }
    (output / "metrics.json").write_text(
        json.dumps(normalize(payload), ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    print(json.dumps(normalize(payload), ensure_ascii=False, indent=2, allow_nan=False))
    print(f"Cascade final backtest: {output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
