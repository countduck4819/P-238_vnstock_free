"""Backtest a frozen final model's daily p_trend Top-K with execution frictions."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from src.evaluation.backtest import BacktestConfig, run_backtest  # noqa: E402
from src.evaluation.wave_model import EvaluationConfig  # noqa: E402


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


def stock_data(directory: Path, symbols: set[str], start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for symbol in sorted(symbols):
        path = directory / f"{symbol}.csv"
        if path.is_file():
            frame = pd.read_csv(path, parse_dates=["date"])
            frame = frame.loc[frame["date"].between(start, end)]
            if not frame.empty:
                frames.append(frame)
    if not frames:
        raise RuntimeError("No OHLCV data available for frozen-model predictions.")
    return pd.concat(frames, ignore_index=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-run", type=Path, required=True)
    parser.add_argument("--top-k", type=int, nargs="+", default=[1, 3, 5, 10])
    parser.add_argument(
        "--holding-sessions",
        type=int,
        help="Override holding horizon; defaults to the frozen label horizon.",
    )
    parser.add_argument(
        "--minimum-probability",
        type=float,
        help="Optional confidence gate applied before daily Top-K ranking.",
    )
    parser.add_argument(
        "--evaluation-config",
        type=Path,
        default=Path("configs/wave_ignition_evaluation_v1.yaml"),
    )
    parser.add_argument("--output-root", type=Path, default=Path("eval/runs/frozen_topk"))
    args = parser.parse_args()
    if any(value <= 0 for value in args.top_k):
        raise ValueError("All Top-K values must be positive.")
    if args.holding_sessions is not None and args.holding_sessions <= 0:
        raise ValueError("holding-sessions must be positive.")
    if args.minimum_probability is not None and not 0 <= args.minimum_probability <= 1:
        raise ValueError("minimum-probability must be in [0, 1].")
    run = args.model_run.resolve()
    predictions = pd.read_parquet(run / "predictions" / "final_test_predictions.parquet")
    predictions["date"] = pd.to_datetime(predictions["date"], errors="raise")
    predictions.rename(columns={"p_strength_conditional": "p_strength"}, inplace=True)
    predictions["p_entry_calibrated_temporal"] = predictions["p_entry_calibrated"]
    manifest = json.loads((run / "model_manifest.json").read_text(encoding="utf-8"))
    dataset_run = Path(manifest["dataset_dependency"]["run"])
    dataset_manifest = json.loads((dataset_run / "dataset_manifest.json").read_text(encoding="utf-8"))
    label_run = Path(dataset_manifest["label_dependency"]["run"])
    label_manifest = json.loads((label_run / "label_manifest.json").read_text(encoding="utf-8"))
    label_horizon = int(label_manifest["configuration"]["horizon"])
    vnindex = pd.read_csv(label_manifest["data_sources"]["vnindex_ohlcv"], parse_dates=["date"])
    evaluation = EvaluationConfig.from_yaml(args.evaluation_config)
    base_config = BacktestConfig.from_dict(evaluation.backtest)
    holding_sessions = args.holding_sessions or label_horizon
    base_config = replace(base_config, maximum_holding_sessions=holding_sessions)
    if args.minimum_probability is not None:
        predictions = predictions.loc[
            predictions["p_entry_calibrated"].ge(args.minimum_probability)
        ].copy()
        if predictions.empty:
            raise RuntimeError("Confidence gate removed every signal.")
    end = min(
        vnindex["date"].max(),
        predictions["date"].max() + pd.Timedelta(days=base_config.maximum_holding_sessions * 3),
    )
    stock = stock_data(
        Path(label_manifest["data_sources"]["stock_ohlcv"]),
        set(predictions["symbol"]),
        predictions["date"].min(),
        end,
    )
    output = args.output_root / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    output.mkdir(parents=True, exist_ok=False)
    results: dict[str, Any] = {}
    for top_k in sorted(set(args.top_k)):
        config = replace(base_config, top_k_per_day=top_k, max_positions=top_k, score_column="p_entry_raw")
        metrics, equity, trades, skipped, yearly = run_backtest(predictions, stock, vnindex, config)
        results[str(top_k)] = {"metrics": metrics, "config": config.__dict__}
        detail = output / f"top_k={top_k}"
        detail.mkdir(parents=True, exist_ok=False)
        equity.to_parquet(detail / "equity_curve.parquet", index=False)
        trades.to_parquet(detail / "trades.parquet", index=False)
        skipped.to_parquet(detail / "skipped_signals.parquet", index=False)
        yearly.to_csv(detail / "yearly_metrics.csv", index=False)
    (output / "metrics.json").write_text(
        json.dumps(
            normalize(
                {
                    "model_run": str(run),
                    "label_horizon": label_horizon,
                    "holding_sessions": holding_sessions,
                    "minimum_probability": args.minimum_probability,
                    "results": results,
                }
            ),
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        ),
        encoding="utf-8",
    )
    print(json.dumps(normalize(results), ensure_ascii=False, indent=2, allow_nan=False))
    print(f"Frozen Top-K backtest: {output.resolve()}")


if __name__ == "__main__":
    main()
