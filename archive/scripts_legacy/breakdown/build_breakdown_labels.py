"""Build fixed-horizon structural-breakdown labels from per-symbol OHLCV files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.labels import BreakdownLabelConfig, label_breakdown_symbol


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--feature-ready", type=Path)
    parser.add_argument(
        "--checkpoint-dir",
        type=Path,
        help="Optional per-symbol Parquet checkpoint directory for resumable builds.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse completed per-symbol checkpoints from --checkpoint-dir.",
    )
    return parser.parse_args()


def load_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path)


def main() -> None:
    args = parse_args()
    if args.resume and args.checkpoint_dir is None:
        raise ValueError("--resume requires --checkpoint-dir.")
    config = BreakdownLabelConfig.from_yaml(args.config)
    ready = None
    if args.feature_ready:
        ready_frame = load_table(args.feature_ready)
        required = {"symbol", "date", "feature_ready"}
        missing = sorted(required - set(ready_frame.columns))
        if missing:
            raise ValueError(f"Feature-ready table is missing: {missing}")
        ready_frame["date"] = pd.to_datetime(ready_frame["date"], errors="raise")
        ready = ready_frame
    outputs: list[pd.DataFrame] = []
    paths = sorted([*args.stock_root.glob("*.csv"), *args.stock_root.glob("*.parquet")])
    if not paths:
        raise FileNotFoundError(f"No CSV/Parquet stock files found under {args.stock_root}")
    skipped: list[str] = []
    completed = 0
    if args.checkpoint_dir is not None:
        args.checkpoint_dir.mkdir(parents=True, exist_ok=True)
    for path in paths:
        symbol = path.stem.upper()
        checkpoint_path = (
            args.checkpoint_dir / f"{symbol}.parquet"
            if args.checkpoint_dir is not None
            else None
        )
        if args.resume and checkpoint_path is not None and checkpoint_path.exists():
            outputs.append(pd.read_parquet(checkpoint_path))
            completed += 1
            if completed % 100 == 0:
                print(f"Resumed {completed:,} symbols", flush=True)
            continue
        stock = load_table(path)
        if "date" not in stock.columns and "time" in stock.columns:
            stock = stock.rename(columns={"time": "date"})
        if not {"date", "open", "close"}.issubset(stock.columns):
            skipped.append(path.name)
            continue
        dates = pd.to_datetime(stock["date"], errors="raise")
        if ready is None:
            feature_ready = pd.Series(True, index=dates)
        else:
            subset = ready.loc[ready["symbol"].eq(symbol)]
            feature_ready = subset.set_index("date")["feature_ready"]
        labeled = label_breakdown_symbol(symbol, stock, feature_ready, config)
        if checkpoint_path is not None:
            temporary = checkpoint_path.with_suffix(".tmp.parquet")
            labeled.to_parquet(temporary, index=False)
            temporary.replace(checkpoint_path)
        outputs.append(labeled)
        completed += 1
        if args.checkpoint_dir is not None and (completed % 100 == 0 or completed == len(paths)):
            print(f"Checkpointed {completed:,}/{len(paths):,} symbols", flush=True)
    if not outputs:
        raise ValueError(f"No OHLCV stock files found under {args.stock_root}")
    result = pd.concat(outputs, ignore_index=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(args.output, index=False)
    if skipped:
        print(f"Skipped non-OHLCV tables: {len(skipped)}")
    print(result["label_status"].value_counts(dropna=False).to_string())
    print(f"Wrote breakdown labels: {args.output.resolve()}")


if __name__ == "__main__":
    main()
