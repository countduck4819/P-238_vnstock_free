"""Build the active H120 continuation labels from clean OHLCV."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from src.labels import (  # noqa: E402
    EVENT_ID_SCHEME,
    ContinuationLabelConfig,
    attach_continuation_weight_components,
    label_continuation_symbol,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path("data/processed/wave_ignition"))
    parser.add_argument(
        "--feature-root", type=Path, default=Path("data/features/wave_ignition")
    )
    parser.add_argument("--feature-run", type=Path)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("data/labels/wave_ignition"))
    parser.add_argument(
        "--sample-weight-policy",
        choices=("baseline", "uniqueness", "uniqueness_date"),
        default="baseline",
        help=(
            "Research policy for the legacy sample_weight column. Class balancing is "
            "deliberately excluded here because it must be fit inside each training fold."
        ),
    )
    return parser.parse_args()


def resolve_feature_run(args: argparse.Namespace) -> Path:
    if args.feature_run is not None:
        return args.feature_run.resolve()
    payload = json.loads((args.feature_root / "latest.json").read_text(encoding="utf-8"))
    return Path(payload["run_directory"]).resolve()


def load_eligibility(feature_run: Path) -> tuple[dict[str, pd.Series], dict[str, Any]]:
    manifest = json.loads((feature_run / "feature_manifest.json").read_text(encoding="utf-8"))
    paths = sorted(feature_run.glob("stock_features/year=*/features.parquet"))
    if not paths:
        raise FileNotFoundError(f"No feature partitions found under {feature_run}")
    frame = pd.concat(
        (pd.read_parquet(path, columns=["symbol", "date", "feature_ready"]) for path in paths),
        ignore_index=True,
    )
    frame["date"] = pd.to_datetime(frame["date"], errors="raise")
    if frame.duplicated(["symbol", "date"]).any():
        raise RuntimeError("Feature eligibility has duplicate symbol/date keys.")
    return {
        symbol: group.set_index("date")["feature_ready"]
        for symbol, group in frame.groupby("symbol", sort=False)
    }, manifest


def write_json(payload: dict[str, Any], path: Path) -> None:
    def normalize(value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): normalize(item) for key, item in value.items()}
        if isinstance(value, (np.integer,)):
            return int(value)
        if isinstance(value, (np.floating, float)):
            return None if not np.isfinite(value) else float(value)
        if isinstance(value, (pd.Timestamp, datetime)):
            return value.isoformat()
        return value

    path.write_text(json.dumps(normalize(payload), ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    config = ContinuationLabelConfig.from_yaml(args.config)
    feature_run = resolve_feature_run(args)
    eligibility, feature_manifest = load_eligibility(feature_run)
    vnindex = pd.read_csv(args.input_dir / "vnindex_ohlcv_1d.csv", parse_dates=["date"])
    paths = sorted((args.input_dir / "stock_ohlcv").glob("*.csv"))
    if not paths:
        raise FileNotFoundError("No clean stock OHLCV files found.")
    frames: list[pd.DataFrame] = []
    for index, path in enumerate(paths, start=1):
        stock = pd.read_csv(path, parse_dates=["date"])
        symbol = str(stock["symbol"].iloc[0])
        labels = label_continuation_symbol(
            symbol,
            stock,
            vnindex,
            eligibility.get(symbol, pd.Series(dtype=bool)),
            config,
        )
        frames.append(labels)
        if index % 100 == 0 or index == len(paths):
            print(f"Labeled {index:,}/{len(paths):,} symbols", flush=True)
    labels = pd.concat(frames, ignore_index=True)
    labels.sort_values(["date", "symbol"], kind="stable", inplace=True)
    labels.reset_index(drop=True, inplace=True)
    labels = attach_continuation_weight_components(
        labels,
        class_balance_mode="none",
        include_date_balance=True,
    )
    labeled_mask = labels["y_entry"].notna()
    if args.sample_weight_policy == "baseline":
        labels.loc[labeled_mask, "sample_weight"] = 1.0
    elif args.sample_weight_policy == "uniqueness":
        labels.loc[labeled_mask, "sample_weight"] = labels.loc[
            labeled_mask, "event_uniqueness_weight"
        ]
    else:
        labels.loc[labeled_mask, "sample_weight"] = labels.loc[
            labeled_mask, "sample_weight_final"
        ]
    labeled = labels.loc[labels["y_entry"].notna()]
    positive = int(labeled["y_entry"].eq(1).sum())
    negative = int(labeled["y_entry"].eq(0).sum())
    quality = {
        "rows": len(labels),
        "symbols": int(labels["symbol"].nunique()),
        "labeled_rows": len(labeled),
        "positive_rows": positive,
        "negative_rows": negative,
        "positive_rate": positive / len(labeled) if len(labeled) else None,
        "unlabeled_rows": int(labels["y_entry"].isna().sum()),
            "label_version": config.label_version,
            "event_id_scheme": EVENT_ID_SCHEME,
            "sample_weight_policy": args.sample_weight_policy,
            "weight_components": {
                "event_concurrency_mean": "mean number of overlapping intervals for the same symbol",
                "event_uniqueness_weight": "mean inverse per-symbol interval concurrency",
                "date_balance_weight": "equal total mass for each decision date",
                "class_balance_weight": "not fit globally; must be fit inside each training fold",
                "sample_weight_final": "uniqueness multiplied by date balance, normalized to mean one",
            },
            "feature_run": str(feature_run),
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    runs_dir = args.output_root / config.label_version / "runs"
    final = runs_dir / run_id
    incomplete = runs_dir / f".incomplete-{run_id}"
    (incomplete / "audit").mkdir(parents=True, exist_ok=False)
    for year, frame in labels.groupby(labels["date"].dt.year, sort=True):
        partition = incomplete / "labels" / f"year={year}"
        partition.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(partition / "labels.parquet", index=False)
    labels.groupby([labels["label_status"], labels["y_entry"].fillna(-1)], dropna=False).size().rename(
        "rows"
    ).reset_index().to_csv(incomplete / "audit" / "label_distribution.csv", index=False)
    write_json(quality, incomplete / "audit" / "label_quality_report.json")
    labels.loc[labels["y_entry"].isna(), ["symbol", "date", "label_status"]].to_parquet(
        incomplete / "audit" / "excluded_rows.parquet", index=False
    )
    write_json(
        {
            "label_version": config.label_version,
            "run_id": run_id,
            "generated_at_utc": quality["generated_at_utc"],
            "configuration": config.to_dict(),
            "feature_dependency": {
                "feature_version": feature_manifest["feature_version"],
                "feature_run": str(feature_run),
                "fields_used": ["symbol", "date", "feature_ready"],
            },
            "data_sources": {
                "stock_ohlcv": str((args.input_dir / "stock_ohlcv").resolve()),
                "vnindex_ohlcv": str((args.input_dir / "vnindex_ohlcv_1d.csv").resolve()),
            },
            "primary_key": ["symbol", "date"],
            "classification_target": "y_entry (continuation)",
            "strength_target": "y_strength (positive rows only)",
            "purge_sessions": config.horizon,
            "event_id_scheme": EVENT_ID_SCHEME,
            "sample_weight_policy": args.sample_weight_policy,
            "class_balance_policy": "must be estimated within each training fold only",
        },
        incomplete / "label_manifest.json",
    )
    incomplete.rename(final)
    write_json(
        {
            "label_version": config.label_version,
            "run_id": run_id,
            "run_directory": str(final.resolve()),
            "generated_at_utc": quality["generated_at_utc"],
        },
        args.output_root / config.label_version / "latest.json",
    )
    print(json.dumps(quality, ensure_ascii=False, indent=2), flush=True)
    print(f"Continuation label store: {final.resolve()}", flush=True)


if __name__ == "__main__":
    main()
