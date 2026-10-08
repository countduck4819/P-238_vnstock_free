"""Derive a training dataset using a validated subset of existing features."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.features import FeatureSelectionConfig  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-dataset-root",
        type=Path,
        default=Path("data/training/wave_ignition/wave_dataset_v1_h150"),
    )
    parser.add_argument("--base-dataset-run", type=Path)
    parser.add_argument(
        "--selection-config",
        type=Path,
        default=Path("configs/wave_ignition_features_v5.yaml"),
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
    latest_path = root / "latest.json"
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    return Path(latest["run_directory"]).resolve()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def derive_partition(
    path: Path,
    source_features: list[str],
    selected_features: list[str],
) -> pd.DataFrame:
    columns = pq.read_schema(path).names
    missing_source = sorted(set(source_features) - set(columns))
    if missing_source:
        raise RuntimeError(f"Source partition is missing manifest features: {missing_source}")
    metadata_columns = [column for column in columns if column not in source_features]
    frame = pd.read_parquet(path, columns=[*metadata_columns, *selected_features])
    if frame.duplicated(["symbol", "date"]).any():
        raise RuntimeError(f"Duplicate symbol/date keys in source partition: {path}")
    return frame


def main() -> None:
    args = parse_args()
    config = FeatureSelectionConfig.from_yaml(args.selection_config)
    base_run = resolve_run(args.base_dataset_run, args.base_dataset_root)
    base_manifest_path = base_run / "dataset_manifest.json"
    base_manifest = json.loads(base_manifest_path.read_text(encoding="utf-8"))
    config.validate_source(base_manifest)

    source_features = list(base_manifest["feature_columns"])
    selected_features = config.selected_features
    partitions = sorted(base_run.glob("dataset/year=*/dataset.parquet"))
    if not partitions:
        raise FileNotFoundError(f"No dataset partitions found under {base_run}")
    if not (base_run / "splits").is_dir():
        raise FileNotFoundError(f"No split directory found under {base_run}")

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    final_run = args.output_root / config.dataset_version / "runs" / run_id
    incomplete = final_run.parent / f".incomplete-{run_id}"
    if final_run.exists() or incomplete.exists():
        raise FileExistsError(f"Dataset run already exists: {run_id}")
    incomplete.mkdir(parents=True)

    row_count = 0
    positive_count = 0
    symbols: set[str] = set()
    null_counts = dict.fromkeys(selected_features, 0)
    first_date: pd.Timestamp | None = None
    last_date: pd.Timestamp | None = None
    for source_path in partitions:
        frame = derive_partition(source_path, source_features, selected_features)
        year_partition = source_path.parent.name
        output_partition = incomplete / "dataset" / year_partition
        output_partition.mkdir(parents=True)
        frame.to_parquet(output_partition / "dataset.parquet", index=False)

        row_count += len(frame)
        positive_count += int(frame["y_entry"].sum())
        symbols.update(frame["symbol"].astype(str).unique())
        for feature, count in frame[selected_features].isna().sum().items():
            null_counts[feature] += int(count)
        partition_first = pd.Timestamp(frame["date"].min())
        partition_last = pd.Timestamp(frame["date"].max())
        first_date = partition_first if first_date is None else min(first_date, partition_first)
        last_date = partition_last if last_date is None else max(last_date, partition_last)
        print(f"Derived {year_partition}: {len(frame):,} rows", flush=True)

    shutil.copytree(base_run / "splits", incomplete / "splits")
    generated_at = datetime.now(UTC).isoformat()
    null_rates = {feature: count / row_count for feature, count in null_counts.items()}
    audit_dir = incomplete / "audit"
    audit_dir.mkdir()
    pd.DataFrame(
        [{"feature": feature, "null_rate": rate} for feature, rate in null_rates.items()]
    ).sort_values("null_rate", ascending=False).to_csv(
        audit_dir / "feature_null_rates.csv",
        index=False,
        encoding="utf-8-sig",
    )
    quality = {
        "dataset_version": config.dataset_version,
        "selection_version": config.selection_version,
        "status": config.status,
        "rows": row_count,
        "symbols": len(symbols),
        "first_date": first_date.date().isoformat() if first_date is not None else None,
        "last_date": last_date.date().isoformat() if last_date is not None else None,
        "feature_count": len(selected_features),
        "positive_rows": positive_count,
        "positive_rate": positive_count / row_count,
        "all_null_features": [name for name, rate in null_rates.items() if rate == 1.0],
        "generated_at_utc": generated_at,
    }
    write_json(quality, audit_dir / "dataset_quality_report.json")

    manifest = {
        "dataset_version": config.dataset_version,
        "run_id": run_id,
        "generated_at_utc": generated_at,
        "status": config.status,
        "protocol": (
            "Exact source rows, labels, weights and temporal split keys; only the "
            "configured feature subset is retained."
        ),
        "base_dataset_dependency": {
            "version": base_manifest["dataset_version"],
            "run": str(base_run),
            "manifest_sha256": sha256_file(base_manifest_path),
        },
        "feature_dependency": {
            "version": config.selection_version,
            "source_feature_version": config.source_feature_version,
            "selection_config": str(args.selection_config.resolve()),
            "selection_config_sha256": sha256_file(args.selection_config),
        },
        "label_dependency": base_manifest["label_dependency"],
        "split_configuration": base_manifest["split_configuration"],
        "feature_columns": selected_features,
        "feature_groups": config.groups_by_name,
        "excluded_features": config.exclusions_by_reason,
        "selection_basis": list(config.selection_basis),
        "selection_guardrails": config.guardrails_by_name,
        "rows": row_count,
        "symbols": len(symbols),
        "positive_rate": positive_count / row_count,
        "feature_null_rates": null_rates,
        "targets": base_manifest["targets"],
        "weights": base_manifest["weights"],
        "primary_key": base_manifest["primary_key"],
        "purge_rule": base_manifest["purge_rule"],
        "test_policy": base_manifest["test_policy"],
    }
    write_json(manifest, incomplete / "dataset_manifest.json")
    incomplete.rename(final_run)
    write_json(
        {
            "dataset_version": config.dataset_version,
            "run_id": run_id,
            "run_directory": str(final_run.resolve()),
            "generated_at_utc": generated_at,
            "status": config.status,
        },
        args.output_root / config.dataset_version / "latest.json",
    )
    print(
        f"Dataset={final_run.resolve()}; rows={row_count:,}; "
        f"features={len(selected_features)}; positive={positive_count / row_count:.4%}",
        flush=True,
    )


if __name__ == "__main__":
    main()
