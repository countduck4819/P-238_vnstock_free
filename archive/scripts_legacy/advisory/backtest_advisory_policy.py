"""Run the cost-aware OOF portfolio simulation on PASS advisory recommendations."""

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--advisory-run", type=Path, required=True)
    parser.add_argument("--model-run", type=Path, required=True)
    parser.add_argument(
        "--evaluation-config",
        type=Path,
        default=Path("configs/wave_ignition_evaluation_v1.yaml"),
    )
    parser.add_argument("--output-root", type=Path, default=Path("eval/runs/wave_advisory"))
    return parser.parse_args()


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


def load_stock_ohlcv(
    directory: Path, symbols: set[str], first_date: pd.Timestamp, last_date: pd.Timestamp
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for symbol in sorted(symbols):
        path = directory / f"{symbol}.csv"
        if path.is_file():
            values = pd.read_csv(path, parse_dates=["date"])
            values = values.loc[values["date"].between(first_date, last_date)]
            if not values.empty:
                frames.append(values)
    if not frames:
        raise RuntimeError("No stock OHLCV was available for the selected PASS rows.")
    return pd.concat(frames, ignore_index=True)


def main() -> None:
    args = parse_args()
    evaluation = EvaluationConfig.from_yaml(args.evaluation_config)
    backtest_config = BacktestConfig.from_dict(evaluation.backtest)
    advisory_summary = json.loads(
        (args.advisory_run / "advisory_summary.json").read_text(encoding="utf-8")
    )
    advisory_score = advisory_summary[
        "deployment_policy_selected_from_all_oof_history"
    ]["ranking"]["score_column"]
    # PASS rows were selected by the advisory ranking; preserve that declared
    # ranking during execution instead of silently re-ranking by wave_score.
    backtest_config = replace(backtest_config, score_column=str(advisory_score))
    signals = pd.read_parquet(args.advisory_run / "advisory_recommendations_oof.parquet")
    signals = signals.loc[signals["advisory_status"].eq("PASS")].copy()
    if signals.empty:
        raise RuntimeError("The advisory policy emitted no PASS rows to backtest.")
    signals["date"] = pd.to_datetime(signals["date"], errors="raise")
    model_manifest = json.loads((args.model_run / "model_manifest.json").read_text(encoding="utf-8"))
    dataset_run = Path(model_manifest["dataset_dependency"]["run"])
    dataset_manifest = json.loads((dataset_run / "dataset_manifest.json").read_text(encoding="utf-8"))
    label_run = Path(dataset_manifest["label_dependency"]["run"])
    label_manifest = json.loads((label_run / "label_manifest.json").read_text(encoding="utf-8"))
    vnindex = pd.read_csv(label_manifest["data_sources"]["vnindex_ohlcv"], parse_dates=["date"])
    # OOF-only backtests stop before the sealed final-test start.
    sealed_start = pd.Timestamp(dataset_manifest["split_configuration"]["test_start"])
    vnindex = vnindex.loc[vnindex["date"] < sealed_start].copy()
    start = signals["date"].min()
    end = min(
        vnindex["date"].max(),
        signals["date"].max() + pd.Timedelta(days=backtest_config.maximum_holding_sessions * 3),
    )
    stock = load_stock_ohlcv(
        Path(label_manifest["data_sources"]["stock_ohlcv"]), set(signals["symbol"]), start, end
    )
    metrics, equity, trades, skipped, yearly = run_backtest(
        signals, stock, vnindex, backtest_config
    )
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    final = args.output_root / "backtests" / run_id
    temporary = final.parent / f".incomplete-{run_id}"
    temporary.mkdir(parents=True, exist_ok=False)
    equity.to_csv(temporary / "equity_curve.csv", index=False, encoding="utf-8-sig")
    trades.to_csv(temporary / "trades.csv", index=False, encoding="utf-8-sig")
    skipped.to_csv(temporary / "skipped_signals.csv", index=False, encoding="utf-8-sig")
    yearly.to_csv(temporary / "yearly.csv", index=False, encoding="utf-8-sig")
    (temporary / "metrics.json").write_text(
        json.dumps(
            normalize(
                {
                    "scope": "nested-temporal-oof-only",
                    "final_test_evaluated": False,
                    "advisory_run": str(args.advisory_run.resolve()),
                    "model_run": str(args.model_run.resolve()),
                    "backtest_config": backtest_config.__dict__,
                    "metrics": metrics,
                }
            ),
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        ),
        encoding="utf-8",
    )
    temporary.rename(final)
    print(json.dumps(normalize(metrics), ensure_ascii=False, indent=2, allow_nan=False))
    print(f"OOF advisory backtest: {final.resolve()}")


if __name__ == "__main__":
    main()
