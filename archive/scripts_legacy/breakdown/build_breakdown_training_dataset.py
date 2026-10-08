"""Build a classifier-only breakdown dataset from an existing horizon store.

The base continuation store supplies the immutable feature matrix and purged
time splits. Breakdown labels replace its targets; every split key is
intersected with resolved breakdown rows, preserving the original embargo.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd


TARGET_COLUMNS = {
    "event_id",
    "event_start_date",
    "label_end_date",
    "label_status",
    "y_entry",
    "y_strength",
    "sample_weight",
    "label_version",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-dataset-run", type=Path, required=True)
    parser.add_argument("--breakdown-labels", type=Path, required=True)
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument(
        "--output-root", type=Path, default=Path("data/training/wave_ignition")
    )
    return parser.parse_args()


def write_json(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    base_run = args.base_dataset_run.resolve()
    base_manifest = json.loads(
        (base_run / "dataset_manifest.json").read_text(encoding="utf-8")
    )
    labels = pd.read_parquet(args.breakdown_labels).copy()
    required = {
        "symbol",
        "date",
        "y_breakdown",
        "label_end_date",
        "label_status",
        "sample_weight",
        "label_version",
    }
    missing = sorted(required - set(labels.columns))
    if missing:
        raise ValueError(f"Breakdown labels are missing: {missing}")
    labels["date"] = pd.to_datetime(labels["date"], errors="raise")
    labels = labels.loc[labels["y_breakdown"].notna()].copy()
    labels["y_entry"] = labels.pop("y_breakdown").astype("int8")
    labels = labels.loc[:, [
        "symbol",
        "date",
        "label_end_date",
        "label_status",
        "y_entry",
        "sample_weight",
        "label_version",
    ]]
    if labels.duplicated(["symbol", "date"]).any():
        raise ValueError("Breakdown labels contain duplicate symbol/date keys.")

    parts: list[pd.DataFrame] = []
    for source in sorted(base_run.glob("dataset/year=*/dataset.parquet")):
        base = pd.read_parquet(source)
        base["date"] = pd.to_datetime(base["date"], errors="raise")
        feature_and_metadata = [column for column in base.columns if column not in TARGET_COLUMNS]
        year_labels = labels.loc[labels["date"].dt.year.eq(int(source.parent.name.split("=")[1]))]
        if year_labels.empty:
            continue
        joined = base.loc[:, feature_and_metadata].merge(
            year_labels,
            on=["symbol", "date"],
            how="inner",
            validate="one_to_one",
        )
        if not joined.empty:
            parts.append(joined)
    if not parts:
        raise RuntimeError("No resolved breakdown labels overlap the base dataset.")
    dataset = pd.concat(parts, ignore_index=True)
    dataset.sort_values(["date", "symbol"], kind="stable", inplace=True)
    dataset.reset_index(drop=True, inplace=True)
    dataset_keys = dataset.loc[:, ["symbol", "date"]]

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    final = args.output_root / args.dataset_version / "runs" / run_id
    incomplete = final.parent / f".incomplete-{run_id}"
    (incomplete / "audit").mkdir(parents=True, exist_ok=False)
    for year, frame in dataset.groupby(dataset["date"].dt.year, sort=True):
        destination = incomplete / "dataset" / f"year={year}"
        destination.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(destination / "dataset.parquet", index=False)

    split_rows: list[dict[str, object]] = []
    for source in sorted((base_run / "splits").glob("*/*_keys.parquet")):
        keys = pd.read_parquet(source)
        keys["date"] = pd.to_datetime(keys["date"], errors="raise")
        retained = keys.merge(dataset_keys, on=["symbol", "date"], how="inner")
        destination = incomplete / "splits" / source.parent.name / source.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        retained.to_parquet(destination, index=False)
        split_rows.append({
            "fold_id": source.parent.name,
            "subset": source.stem.replace("_keys", ""),
            "rows": int(len(retained)),
            "positive_rows": int(
                retained.merge(
                    dataset.loc[:, ["symbol", "date", "y_entry"]],
                    on=["symbol", "date"],
                    how="left",
                )["y_entry"].sum()
            ),
        })
    split_summary = pd.DataFrame(split_rows)
    split_summary.to_csv(incomplete / "audit/split_summary.csv", index=False)
    quality = {
        "rows": int(len(dataset)),
        "symbols": int(dataset["symbol"].nunique()),
        "first_date": dataset["date"].min().isoformat(),
        "last_date": dataset["date"].max().isoformat(),
        "positive_rows": int(dataset["y_entry"].sum()),
        "positive_rate": float(dataset["y_entry"].mean()),
    }
    write_json(quality, incomplete / "audit/dataset_quality_report.json")
    manifest = {
        "dataset_version": args.dataset_version,
        "run_id": run_id,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "base_dataset_dependency": str(base_run),
        "breakdown_label_dependency": str(args.breakdown_labels.resolve()),
        "feature_columns": base_manifest["feature_columns"],
        "primary_key": ["symbol", "date"],
        "classification_target": "y_entry (structural breakdown)",
        "split_policy": "intersection with base purged horizon splits",
        "final_test_policy": "sealed; trainer does not evaluate final test",
    }
    write_json(manifest, incomplete / "dataset_manifest.json")
    incomplete.rename(final)
    write_json(
        {
            "dataset_version": args.dataset_version,
            "run_id": run_id,
            "run_directory": str(final.resolve()),
        },
        args.output_root / args.dataset_version / "latest.json",
    )
    print(json.dumps(quality, indent=2))
    print(split_summary.to_string(index=False))
    print(f"Breakdown training dataset: {final.resolve()}")


if __name__ == "__main__":
    main()
