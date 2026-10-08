"""Rebuild the pinned H120 ranker dataset after a versioned label refresh.

The feature rows are copied from an existing pinned dataset run.  Only label
columns are replaced, then all purged walk-forward split keys are regenerated.
This prevents a new experiment generation from silently training v3 protocol
code on v2 label rows.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.training.splits import SplitConfig, build_purged_walk_forward_splits


LABEL_COLUMNS = [
    "label_version", "label_status", "y_entry", "y_strength", "sample_weight",
    "event_id", "event_start_date", "entry_date", "label_end_date",
    "event_concurrency_mean", "event_uniqueness_weight", "date_balance_weight",
    "class_balance_weight", "sample_weight_final",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dataset-run", type=Path, required=True)
    parser.add_argument("--label-run", type=Path, required=True)
    parser.add_argument("--calendar", type=Path, required=True)
    parser.add_argument(
        "--split-config",
        type=Path,
        default=Path("configs/wave_continuation_training_splits_h120.yaml"),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("data/training/wave_ignition_snapshot/wave_dataset_continuation_h120_v3"),
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_partitions(root: Path, filename: str) -> pd.DataFrame:
    paths = sorted(root.glob(f"year=*/{filename}"))
    if not paths:
        raise FileNotFoundError(f"No {filename} partitions under {root}")
    return pd.concat((pd.read_parquet(path) for path in paths), ignore_index=True)


def main() -> int:
    args = parse_args()
    source = args.source_dataset_run.resolve()
    label_run = args.label_run.resolve()
    source_manifest_path = source / "dataset_manifest.json"
    label_manifest_path = label_run / "label_manifest.json"
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    label_manifest = json.loads(label_manifest_path.read_text(encoding="utf-8"))
    labels = load_partitions(label_run / "labels", "labels.parquet")
    features = load_partitions(source / "dataset", "dataset.parquet")
    keys = ["symbol", "date"]
    if labels.duplicated(keys).any() or features.duplicated(keys).any():
        raise ValueError("Source dataset or label refresh contains duplicate symbol/date keys.")
    old_label_columns = [column for column in LABEL_COLUMNS if column in features.columns]
    rebuilt = features.drop(columns=old_label_columns).merge(
        labels.loc[:, [*keys, *LABEL_COLUMNS]],
        on=keys,
        how="left",
        validate="one_to_one",
    )
    missing_labels = int(rebuilt["label_version"].isna().sum())
    if missing_labels:
        raise ValueError(f"{missing_labels:,} feature rows have no corresponding refreshed label.")
    rebuilt["date"] = pd.to_datetime(rebuilt["date"], errors="raise")
    rebuilt["label_end_date"] = pd.to_datetime(rebuilt["label_end_date"], errors="raise")
    dataset = rebuilt.loc[rebuilt["y_entry"].notna()].copy()
    if dataset.empty:
        raise ValueError("Refreshed label join yielded no labeled feature-ready rows.")
    if dataset["label_version"].nunique() != 1:
        raise ValueError("Refreshed dataset must contain exactly one label version.")
    split_config = SplitConfig.from_yaml(args.split_config)
    calendar = pd.read_csv(args.calendar, parse_dates=["date"])["date"]
    splits, summary = build_purged_walk_forward_splits(dataset, pd.DatetimeIndex(calendar), split_config)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    final = args.output_root.resolve() / "runs" / run_id
    incomplete = final.parent / f".incomplete-{run_id}"
    (incomplete / "audit").mkdir(parents=True, exist_ok=False)
    for year, frame in dataset.groupby(dataset["date"].dt.year, sort=True):
        target = incomplete / "dataset" / f"year={year}"
        target.mkdir(parents=True, exist_ok=True)
        frame.sort_values(keys, kind="stable").to_parquet(target / "dataset.parquet", index=False)
    for fold_id, members in splits.items():
        for subset, frame in members.items():
            target = incomplete / "splits" / fold_id
            target.mkdir(parents=True, exist_ok=True)
            frame.to_parquet(target / f"{subset}_keys.parquet", index=False)
    summary.to_csv(incomplete / "audit" / "split_summary.csv", index=False)
    quality = {
        "rows": int(len(dataset)),
        "symbols": int(dataset["symbol"].nunique()),
        "first_date": str(dataset["date"].min().date()),
        "last_date": str(dataset["date"].max().date()),
        "positive_rows": int(dataset["y_entry"].eq(1).sum()),
        "negative_rows": int(dataset["y_entry"].eq(0).sum()),
        "positive_rate": float(dataset["y_entry"].mean()),
        "duplicate_symbol_dates": int(dataset.duplicated(keys).sum()),
        "label_version": str(dataset["label_version"].iloc[0]),
    }
    (incomplete / "audit" / "dataset_quality_report.json").write_text(
        json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    manifest = {
        "dataset_version": f"{split_config.dataset_version}_v3_eventweights",
        "run_id": run_id,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "feature_dependency": source_manifest["feature_dependency"],
        "label_dependency": {"version": quality["label_version"], "run": str(label_run)},
        "split_configuration": split_config.to_dict(),
        "source_dataset_run": str(source),
        "source_checksums": {
            "source_dataset_manifest": sha256(source_manifest_path),
            "label_manifest": sha256(label_manifest_path),
            "split_config": sha256(args.split_config),
            "calendar": sha256(args.calendar),
        },
        "quality": quality,
    }
    (incomplete / "dataset_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    incomplete.rename(final)
    print(json.dumps({"status": "ok", "run_directory": str(final), **quality}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
