"""Build versioned Wave Event labels from cleaned OHLCV and feature eligibility."""

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

from src.labels import WaveLabelConfig, label_symbol  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("data/processed/wave_ignition"),
    )
    parser.add_argument(
        "--feature-root",
        type=Path,
        default=Path("data/features/wave_ignition/wave_ignition_v1"),
    )
    parser.add_argument("--feature-run", type=Path)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/wave_ignition_labels_v1.yaml"),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("data/labels/wave_ignition"),
    )
    return parser.parse_args()


def write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_feature_run(args: argparse.Namespace) -> Path:
    if args.feature_run is not None:
        return args.feature_run.resolve()
    latest = json.loads((args.feature_root / "latest.json").read_text(encoding="utf-8"))
    return Path(latest["run_directory"])


def load_feature_eligibility(feature_run: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    manifest = json.loads(
        (feature_run / "feature_manifest.json").read_text(encoding="utf-8")
    )
    partitions = sorted(feature_run.glob("stock_features/year=*/features.parquet"))
    if not partitions:
        raise FileNotFoundError(f"No feature partitions found in {feature_run}")
    eligibility = pd.concat(
        [
            pd.read_parquet(
                partition,
                columns=["symbol", "date", "feature_ready"],
            )
            for partition in partitions
        ],
        ignore_index=True,
    )
    eligibility["date"] = pd.to_datetime(eligibility["date"])
    if eligibility.duplicated(["symbol", "date"]).any():
        raise ValueError("Feature eligibility contains duplicate symbol/date keys.")
    return eligibility, manifest


def build_audit_tables(
    labels: pd.DataFrame,
    sector_column: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    distribution = (
        labels.groupby("label_status", dropna=False)
        .size()
        .rename("rows")
        .reset_index()
        .sort_values("rows", ascending=False)
    )
    labeled = labels.loc[labels["y_entry"].notna()].copy()
    labeled["year"] = labeled["date"].dt.year
    yearly = (
        labeled.groupby(["year", "y_entry"]).size().unstack(fill_value=0).reset_index()
    )
    yearly.columns = [
        "year" if column == "year" else f"y_entry_{int(column)}"
        for column in yearly.columns
    ]
    sector = (
        labeled.groupby([sector_column, "y_entry"])
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )
    sector.columns = [
        sector_column if column == sector_column else f"y_entry_{int(column)}"
        for column in sector.columns
    ]

    metric_columns = [
        "entry_price",
        "upper_barrier",
        "lower_barrier",
        "volatility_at_t",
        "mfe",
        "mae",
        "terminal_return",
        "market_return",
        "excess_market_return",
        "persistence",
        "trend_efficiency",
        "future_coverage",
        "candidate_strength",
        "y_strength",
        "sample_weight",
    ]
    non_finite_counts: dict[str, int] = {}
    for column in metric_columns:
        mask = labels[column].notna() & ~np.isfinite(labels[column])
        if mask.any():
            non_finite_counts[column] = int(mask.sum())

    positives = int(labels["y_entry"].eq(1).sum())
    negatives = int(labels["y_entry"].eq(0).sum())
    report = {
        "rows": len(labels),
        "symbols": int(labels["symbol"].nunique()),
        "first_date": labels["date"].min().date().isoformat(),
        "last_date": labels["date"].max().date().isoformat(),
        "labeled_rows": positives + negatives,
        "positive_rows": positives,
        "negative_rows": negatives,
        "positive_rate": positives / (positives + negatives) if positives + negatives else None,
        "unlabeled_rows": int(labels["y_entry"].isna().sum()),
        "events": int(labels["event_id"].dropna().nunique()),
        "duplicate_symbol_dates": int(labels.duplicated(["symbol", "date"]).sum()),
        "non_finite_counts": non_finite_counts,
        "strength_min": labels["y_strength"].min(),
        "strength_max": labels["y_strength"].max(),
        "strength_mean": labels["y_strength"].mean(),
    }
    return distribution, yearly, sector, report


def main() -> None:
    args = parse_args()
    config = WaveLabelConfig.from_yaml(args.config)
    feature_run = resolve_feature_run(args)
    eligibility, feature_manifest = load_feature_eligibility(feature_run)
    eligibility_by_symbol = {
        symbol: group.set_index("date")["feature_ready"]
        for symbol, group in eligibility.groupby("symbol", sort=False)
    }

    vnindex = pd.read_csv(args.input_dir / "vnindex_ohlcv_1d.csv", parse_dates=["date"])
    industry = pd.read_csv(args.input_dir / "industry_map_icb.csv", dtype="string")
    sector_column = f"icb_level_{feature_manifest['configuration']['industry_level']}_code"
    sector_map = industry.set_index("symbol")[sector_column]
    stock_paths = sorted((args.input_dir / "stock_ohlcv").glob("*.csv"))
    if not stock_paths:
        raise FileNotFoundError("No cleaned stock OHLCV files were found.")

    label_frames: list[pd.DataFrame] = []
    event_frames: list[pd.DataFrame] = []
    for index, path in enumerate(stock_paths, start=1):
        stock = pd.read_csv(path, parse_dates=["date"])
        symbol = str(stock["symbol"].iloc[0])
        ready = eligibility_by_symbol.get(
            symbol,
            pd.Series(dtype=bool, index=pd.DatetimeIndex([], name="date")),
        )
        labels, events = label_symbol(symbol, stock, vnindex, ready, config)
        labels[sector_column] = sector_map.get(symbol, pd.NA)
        label_frames.append(labels)
        if not events.empty:
            events[sector_column] = sector_map.get(symbol, pd.NA)
            event_frames.append(events)
        if index % 100 == 0 or index == len(stock_paths):
            print(f"Labeled {index:,}/{len(stock_paths):,} symbols", flush=True)

    labels = pd.concat(label_frames, ignore_index=True)
    labels.sort_values(["date", "symbol"], kind="stable", inplace=True)
    labels.reset_index(drop=True, inplace=True)
    events = pd.concat(event_frames, ignore_index=True) if event_frames else pd.DataFrame()
    distribution, yearly, sector, quality = build_audit_tables(labels, sector_column)
    if quality["duplicate_symbol_dates"]:
        raise RuntimeError("Label output contains duplicate symbol/date keys.")
    if quality["non_finite_counts"]:
        raise RuntimeError(f"Non-finite label metrics detected: {quality['non_finite_counts']}")
    if quality["strength_min"] is not None and not (
        0 <= quality["strength_min"] <= quality["strength_max"] <= 1
    ):
        raise RuntimeError("y_strength is outside [0, 1].")

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    runs_dir = args.output_root / config.label_version / "runs"
    final_run_dir = runs_dir / run_id
    run_dir = runs_dir / f".incomplete-{run_id}"
    audit_dir = run_dir / "audit"
    audit_dir.mkdir(parents=True, exist_ok=False)

    label_dir = run_dir / "labels"
    for year, frame in labels.groupby(labels["date"].dt.year, sort=True):
        partition = label_dir / f"year={year}"
        partition.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(partition / "labels.parquet", index=False)
    events.to_parquet(run_dir / "events.parquet", index=False)
    distribution.to_csv(
        audit_dir / "label_distribution.csv", index=False, encoding="utf-8-sig"
    )
    yearly.to_csv(
        audit_dir / "yearly_distribution.csv", index=False, encoding="utf-8-sig"
    )
    sector.to_csv(
        audit_dir / "sector_distribution.csv", index=False, encoding="utf-8-sig"
    )
    excluded = labels.loc[
        labels["y_entry"].isna(),
        ["symbol", "date", "label_status", "event_id", "future_coverage"],
    ]
    excluded.to_parquet(audit_dir / "excluded_rows.parquet", index=False)

    generated_at = datetime.now(UTC).isoformat()
    quality["generated_at_utc"] = generated_at
    quality["feature_run"] = str(feature_run)
    quality["feature_version"] = feature_manifest["feature_version"]
    quality["label_version"] = config.label_version
    write_json(quality, audit_dir / "label_quality_report.json")
    manifest = {
        "label_version": config.label_version,
        "run_id": run_id,
        "generated_at_utc": generated_at,
        "configuration": config.to_dict(),
        "feature_dependency": {
            "feature_version": feature_manifest["feature_version"],
            "feature_run": str(feature_run),
            "fields_used": ["symbol", "date", "feature_ready"],
            "wave_feature_score_used": False,
        },
        "data_sources": {
            "stock_ohlcv": str((args.input_dir / "stock_ohlcv").resolve()),
            "vnindex_ohlcv": str(
                (args.input_dir / "vnindex_ohlcv_1d.csv").resolve()
            ),
            "industry_map": str((args.input_dir / "industry_map_icb.csv").resolve()),
        },
        "primary_key": ["symbol", "date"],
        "classification_target": "y_entry",
        "strength_target": "y_strength (positive labels only)",
        "purge_sessions": config.horizon,
        "partitioning": "labels/year=YYYY/labels.parquet",
    }
    write_json(manifest, run_dir / "label_manifest.json")
    run_dir.rename(final_run_dir)
    write_json(
        {
            "label_version": config.label_version,
            "run_id": run_id,
            "run_directory": str(final_run_dir.resolve()),
            "generated_at_utc": generated_at,
        },
        args.output_root / config.label_version / "latest.json",
    )
    print(json.dumps(quality, ensure_ascii=False, indent=2), flush=True)
    print(f"Label store: {final_run_dir.resolve()}", flush=True)


if __name__ == "__main__":
    main()
