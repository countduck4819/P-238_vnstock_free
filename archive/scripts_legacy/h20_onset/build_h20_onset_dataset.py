"""Join versioned features and labels, then create purged time-aware splits."""

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

from src.training import SplitConfig, build_purged_walk_forward_splits  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--feature-root",
        type=Path,
        default=Path("data/features/wave_ignition/wave_ignition_v1"),
    )
    parser.add_argument("--feature-run", type=Path)
    parser.add_argument(
        "--label-root",
        type=Path,
        default=Path("data/labels/wave_ignition/wave_label_v1"),
    )
    parser.add_argument("--label-run", type=Path)
    parser.add_argument(
        "--vnindex-file",
        type=Path,
        default=Path("data/processed/wave_ignition/vnindex_ohlcv_1d.csv"),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/wave_ignition_training_splits_v1.yaml"),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("data/training/wave_ignition"),
    )
    return parser.parse_args()


def write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_run(explicit_run: Path | None, root: Path) -> Path:
    if explicit_run is not None:
        return explicit_run.resolve()
    latest = json.loads((root / "latest.json").read_text(encoding="utf-8"))
    return Path(latest["run_directory"])


def load_manifest(run: Path, filename: str) -> dict[str, Any]:
    return json.loads((run / filename).read_text(encoding="utf-8"))


def partition_year(path: Path) -> int:
    for parent in path.parents:
        if parent.name.startswith("year="):
            return int(parent.name.split("=", maxsplit=1)[1])
    raise ValueError(f"Cannot infer year partition from {path}")


def build_joined_dataset(
    feature_run: Path,
    label_run: Path,
    feature_manifest: dict[str, Any],
) -> pd.DataFrame:
    feature_columns = feature_manifest["feature_columns"]
    industry_level = feature_manifest["configuration"]["industry_level"]
    metadata_columns = [
        "symbol",
        "date",
        f"icb_level_{industry_level}_code",
        f"icb_level_{industry_level}_name",
        "feature_ready",
        "feature_version",
    ]
    label_columns = [
        "symbol",
        "date",
        "event_id",
        "event_start_date",
        "label_end_date",
        "label_status",
        "y_entry",
        "y_strength",
        "sample_weight",
        "label_version",
    ]
    label_partitions = {
        partition_year(path): path
        for path in label_run.glob("labels/year=*/labels.parquet")
    }
    feature_partitions = sorted(
        feature_run.glob("stock_features/year=*/features.parquet")
    )
    joined: list[pd.DataFrame] = []
    expected_labels = 0
    for feature_path in feature_partitions:
        year = partition_year(feature_path)
        label_path = label_partitions.get(year)
        if label_path is None:
            continue
        labels = pd.read_parquet(label_path, columns=label_columns)
        labels = labels.loc[labels["y_entry"].notna()].copy()
        if labels.empty:
            continue
        expected_labels += len(labels)
        features = pd.read_parquet(
            feature_path,
            columns=[*metadata_columns, *feature_columns],
        )
        frame = features.merge(
            labels,
            on=["symbol", "date"],
            how="inner",
            validate="one_to_one",
        )
        if len(frame) != len(labels):
            raise RuntimeError(
                f"Feature/label join lost {len(labels) - len(frame)} rows in {year}."
            )
        joined.append(frame)
        print(f"Joined year {year}: {len(frame):,} rows", flush=True)
    if not joined:
        raise RuntimeError("No trainable feature/label rows were joined.")
    dataset = pd.concat(joined, ignore_index=True)
    if len(dataset) != expected_labels:
        raise RuntimeError("Joined dataset row count does not match trainable labels.")
    dataset.sort_values(["date", "symbol"], kind="stable", inplace=True)
    dataset.reset_index(drop=True, inplace=True)
    return dataset


def validate_dataset(
    dataset: pd.DataFrame,
    feature_columns: list[str],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if dataset.duplicated(["symbol", "date"]).any():
        raise RuntimeError("Training dataset contains duplicate symbol/date keys.")
    if not dataset["feature_ready"].all():
        raise RuntimeError("Training dataset contains rows that are not feature_ready.")
    if not dataset["y_entry"].isin([0, 1]).all():
        raise RuntimeError("y_entry contains values outside {0, 1}.")
    positive = dataset["y_entry"].eq(1)
    if dataset.loc[positive, "y_strength"].isna().any():
        raise RuntimeError("Positive rows contain missing y_strength.")
    if dataset.loc[~positive, "y_strength"].notna().any():
        raise RuntimeError("Negative rows contain non-null y_strength.")

    non_finite_counts: dict[str, int] = {}
    for column in feature_columns:
        values = dataset[column]
        mask = values.notna() & ~np.isfinite(values)
        if mask.any():
            non_finite_counts[column] = int(mask.sum())
    if non_finite_counts:
        raise RuntimeError(f"Non-finite features detected: {non_finite_counts}")

    null_rates = (
        dataset[feature_columns]
        .isna()
        .mean()
        .rename("null_rate")
        .sort_values(ascending=False)
        .reset_index()
        .rename(columns={"index": "feature"})
    )
    positives = int(positive.sum())
    negatives = int((~positive).sum())
    report = {
        "rows": len(dataset),
        "symbols": int(dataset["symbol"].nunique()),
        "first_date": dataset["date"].min().date().isoformat(),
        "last_date": dataset["date"].max().date().isoformat(),
        "feature_count": len(feature_columns),
        "positive_rows": positives,
        "negative_rows": negatives,
        "positive_rate": positives / len(dataset),
        "duplicate_symbol_dates": 0,
        "non_finite_feature_counts": {},
        "all_null_features": null_rates.loc[null_rates["null_rate"].eq(1), "feature"].tolist(),
    }
    return null_rates, report


def enrich_split_summary(summary: pd.DataFrame) -> pd.DataFrame:
    summary = summary.copy()
    summary["recommended_positive_class_weight"] = np.divide(
        summary["negative_rows"],
        summary["positive_rows"],
        out=np.full(len(summary), np.nan),
        where=summary["positive_rows"].to_numpy() > 0,
    )
    for column in ("first_date", "last_date", "maximum_label_end_date"):
        summary[column] = pd.to_datetime(summary[column]).dt.date.astype("string")
    return summary


def main() -> None:
    args = parse_args()
    config = SplitConfig.from_yaml(args.config)
    feature_run = resolve_run(args.feature_run, args.feature_root)
    label_run = resolve_run(args.label_run, args.label_root)
    feature_manifest = load_manifest(feature_run, "feature_manifest.json")
    label_manifest = load_manifest(label_run, "label_manifest.json")
    dependency = label_manifest["feature_dependency"]
    if Path(dependency["feature_run"]).resolve() != feature_run.resolve():
        raise RuntimeError("Label store was not generated from the selected feature run.")

    dataset = build_joined_dataset(feature_run, label_run, feature_manifest)
    feature_columns = feature_manifest["feature_columns"]
    null_rates, quality = validate_dataset(dataset, feature_columns)
    vnindex = pd.read_csv(args.vnindex_file, usecols=["date"], parse_dates=["date"])
    splits, split_summary = build_purged_walk_forward_splits(
        dataset[["symbol", "date", "label_end_date", "y_entry"]],
        pd.DatetimeIndex(vnindex["date"]),
        config,
    )
    split_summary = enrich_split_summary(split_summary)

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    runs_dir = args.output_root / config.dataset_version / "runs"
    final_run_dir = runs_dir / run_id
    run_dir = runs_dir / f".incomplete-{run_id}"
    audit_dir = run_dir / "audit"
    audit_dir.mkdir(parents=True, exist_ok=False)

    dataset_dir = run_dir / "dataset"
    for year, frame in dataset.groupby(dataset["date"].dt.year, sort=True):
        partition = dataset_dir / f"year={year}"
        partition.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(partition / "dataset.parquet", index=False)

    split_dir = run_dir / "splits"
    for fold_id, subsets in splits.items():
        fold_dir = split_dir / fold_id
        fold_dir.mkdir(parents=True, exist_ok=True)
        for subset, keys in subsets.items():
            keys.to_parquet(fold_dir / f"{subset}_keys.parquet", index=False)

    null_rates.to_csv(
        audit_dir / "feature_null_rates.csv", index=False, encoding="utf-8-sig"
    )
    split_summary.to_csv(
        audit_dir / "split_summary.csv", index=False, encoding="utf-8-sig"
    )
    generated_at = datetime.now(UTC).isoformat()
    quality.update(
        {
            "generated_at_utc": generated_at,
            "dataset_version": config.dataset_version,
            "feature_version": feature_manifest["feature_version"],
            "label_version": label_manifest["label_version"],
        }
    )
    write_json(quality, audit_dir / "dataset_quality_report.json")
    manifest = {
        "dataset_version": config.dataset_version,
        "run_id": run_id,
        "generated_at_utc": generated_at,
        "feature_dependency": {
            "version": feature_manifest["feature_version"],
            "run": str(feature_run),
        },
        "label_dependency": {
            "version": label_manifest["label_version"],
            "run": str(label_run),
        },
        "split_configuration": config.to_dict(),
        "feature_columns": feature_columns,
        "targets": {
            "classification": "y_entry",
            "strength": "y_strength (positive rows only)",
        },
        "weights": {
            "base": "sample_weight",
            "class_weight": "Compute per fold from audit/split_summary.csv",
        },
        "primary_key": ["symbol", "date"],
        "dataset_partitioning": "dataset/year=YYYY/dataset.parquet",
        "split_storage": "Key files join to dataset on symbol,date",
        "purge_rule": "train.label_end_date < embargo_boundary",
        "test_policy": "Final untouched holdout beginning at test_start",
    }
    write_json(manifest, run_dir / "dataset_manifest.json")
    run_dir.rename(final_run_dir)
    write_json(
        {
            "dataset_version": config.dataset_version,
            "run_id": run_id,
            "run_directory": str(final_run_dir.resolve()),
            "generated_at_utc": generated_at,
        },
        args.output_root / config.dataset_version / "latest.json",
    )
    print(json.dumps(quality, ensure_ascii=False, indent=2), flush=True)
    print(split_summary.to_string(index=False), flush=True)
    print(f"Training dataset: {final_run_dir.resolve()}", flush=True)


if __name__ == "__main__":
    main()
