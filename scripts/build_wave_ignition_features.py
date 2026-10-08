"""Build the versioned Wave Ignition feature store from cleaned daily data."""

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

from src.features import FeatureConfig, build_feature_tables  # noqa: E402

RAW_COLUMNS = {"open", "high", "low", "close", "volume"}
METADATA_COLUMNS = {
    "symbol",
    "date",
    "feature_version",
    "feature_ready",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("data/processed/wave_ignition"),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/wave_ignition_features_v2.yaml"),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("data/features/wave_ignition"),
    )
    return parser.parse_args()


def load_stock_files(directory: Path) -> pd.DataFrame:
    paths = sorted(directory.glob("*.csv"))
    if not paths:
        raise FileNotFoundError(f"No cleaned stock CSV files found in {directory}")
    frames: list[pd.DataFrame] = []
    for index, path in enumerate(paths, start=1):
        frame = pd.read_csv(
            path,
            dtype={"symbol": "string"},
            parse_dates=["date"],
        )
        frames.append(frame)
        if index % 250 == 0 or index == len(paths):
            print(f"Loaded {index:,}/{len(paths):,} stock files", flush=True)
    return pd.concat(frames, ignore_index=True)


def write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def feature_columns(frame: pd.DataFrame, industry_level: int) -> list[str]:
    industry_columns = {
        f"icb_level_{industry_level}_code",
        f"icb_level_{industry_level}_name",
    }
    excluded = RAW_COLUMNS | METADATA_COLUMNS | industry_columns
    return [
        column for column in frame.columns if column not in excluded and pd.api.types.is_numeric_dtype(frame[column])
    ]


def build_audit(
    stock_features: pd.DataFrame,
    selected_features: list[str],
    config: FeatureConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    null_rates = (
        stock_features[selected_features]
        .isna()
        .mean()
        .rename("null_rate")
        .sort_values(ascending=False)
        .reset_index()
        .rename(columns={"index": "feature"})
    )

    non_finite_mask = pd.Series(False, index=stock_features.index)
    non_finite_counts: dict[str, int] = {}
    for column in selected_features:
        values = stock_features[column]
        mask = values.notna() & ~np.isfinite(values)
        count = int(mask.sum())
        if count:
            non_finite_counts[column] = count
            non_finite_mask |= mask

    core_scores = [
        "market_regime_score",
        "sector_strength_score",
        "stock_ignition_score",
        "leader_score",
    ]
    unavailable = stock_features.loc[
        ~stock_features["feature_ready"],
        [
            "symbol",
            "date",
            "coverage_20",
            "coverage_60",
            "coverage_120",
            "quality_score",
            *core_scores,
        ],
    ].copy()
    unavailable["low_quality"] = unavailable["quality_score"].lt(70) | unavailable["quality_score"].isna()
    unavailable["market_unavailable"] = unavailable["market_regime_score"].isna()
    unavailable["sector_unavailable"] = unavailable["sector_strength_score"].isna()
    unavailable["stock_score_unavailable"] = unavailable["stock_ignition_score"].isna()
    unavailable["leader_unavailable"] = unavailable["leader_score"].isna()

    quality_gate_masks = {
        "coverage_60_below_minimum": stock_features["coverage_60"].lt(config.quality_min_coverage_60),
        "coverage_120_below_minimum": stock_features["coverage_120"].lt(config.quality_min_coverage_120),
        "zero_volume_ratio_60_above_maximum": stock_features["zero_volume_ratio_60"].gt(
            config.quality_max_zero_volume_ratio_60
        ),
        "stale_sessions_above_maximum": stock_features["stale_sessions"].fillna(np.inf).gt(
            config.quality_max_stale_sessions
        ),
        "corporate_action_cooldown": stock_features["corporate_action_recent"].fillna(True),
    }

    report = {
        "rows": len(stock_features),
        "symbols": int(stock_features["symbol"].nunique()),
        "first_date": stock_features["date"].min().date().isoformat(),
        "last_date": stock_features["date"].max().date().isoformat(),
        "feature_count": len(selected_features),
        "ready_rows": int(stock_features["feature_ready"].sum()),
        "unavailable_rows": len(unavailable),
        "non_finite_rows": int(non_finite_mask.sum()),
        "non_finite_counts": non_finite_counts,
        "duplicate_symbol_dates": int(stock_features.duplicated(["symbol", "date"]).sum()),
        "unsorted": not stock_features.sort_values(["date", "symbol"])[["date", "symbol"]]
        .reset_index(drop=True)
        .equals(stock_features[["date", "symbol"]].reset_index(drop=True)),
        "quality_gate_configuration": {
            "enabled": config.hard_quality_gates,
            "min_coverage_60": config.quality_min_coverage_60,
            "min_coverage_120": config.quality_min_coverage_120,
            "max_zero_volume_ratio_60": config.quality_max_zero_volume_ratio_60,
            "max_stale_sessions": config.quality_max_stale_sessions,
            "corporate_action_cooldown": config.corporate_action_cooldown,
        },
        "quality_gate_failure_counts_non_exclusive": {
            name: int(mask.fillna(True).sum()) for name, mask in quality_gate_masks.items()
        },
    }
    non_finite = stock_features.loc[non_finite_mask, ["symbol", "date", *selected_features]]
    return null_rates, unavailable, {**report, "non_finite_frame": non_finite}


def main() -> None:
    args = parse_args()
    config = FeatureConfig.from_yaml(args.config)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    runs_dir = args.output_root / config.feature_version / "runs"
    final_run_dir = runs_dir / run_id
    run_dir = runs_dir / f".incomplete-{run_id}"
    audit_dir = run_dir / "audit"
    run_dir.mkdir(parents=True, exist_ok=False)
    audit_dir.mkdir(parents=True, exist_ok=False)

    stock = load_stock_files(args.input_dir / "stock_ohlcv")
    vnindex = pd.read_csv(args.input_dir / "vnindex_ohlcv_1d.csv", parse_dates=["date"])
    industry = pd.read_csv(
        args.input_dir / "industry_map_icb.csv",
        dtype="string",
    )
    print(f"Computing features for {stock['symbol'].nunique():,} symbols...", flush=True)
    stock_features, market_features, sector_features = build_feature_tables(
        stock,
        vnindex,
        industry,
        config,
    )

    selected_features = feature_columns(stock_features, config.industry_level)
    null_rates, unavailable, quality = build_audit(stock_features, selected_features, config)
    non_finite = quality.pop("non_finite_frame")
    if quality["non_finite_rows"]:
        raise RuntimeError(f"Feature generation produced {quality['non_finite_rows']} non-finite rows.")
    if quality["duplicate_symbol_dates"] or quality["unsorted"]:
        raise RuntimeError("Feature store key uniqueness or ordering validation failed.")

    stock_feature_dir = run_dir / "stock_features"
    for year, frame in stock_features.groupby(stock_features["date"].dt.year, sort=True):
        partition = stock_feature_dir / f"year={year}"
        partition.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(partition / "features.parquet", index=False)
    market_features.to_parquet(run_dir / "market_features.parquet", index=False)
    sector_features.to_parquet(run_dir / "sector_features.parquet", index=False)
    null_rates.to_csv(audit_dir / "feature_null_rates.csv", index=False, encoding="utf-8-sig")
    unavailable.to_parquet(audit_dir / "unavailable_rows.parquet", index=False)
    non_finite.to_parquet(audit_dir / "non_finite_rows.parquet", index=False)

    generated_at = datetime.now(UTC).isoformat()
    quality["generated_at_utc"] = generated_at
    quality["ready_rate"] = quality["ready_rows"] / quality["rows"]
    quality["price_adjustment_policy"] = config.price_adjustment_policy
    quality["promotion_status"] = (
        "blocked_unverified_price_policy"
        if config.price_adjustment_policy not in {"raw", "adjusted"}
        else "candidate_for_training"
    )
    write_json(quality, audit_dir / "feature_quality_report.json")
    manifest = {
        "feature_version": config.feature_version,
        "run_id": run_id,
        "generated_at_utc": generated_at,
        "data_sources": {
            "stock_ohlcv": str((args.input_dir / "stock_ohlcv").resolve()),
            "vnindex_ohlcv": str((args.input_dir / "vnindex_ohlcv_1d.csv").resolve()),
            "industry_map": str((args.input_dir / "industry_map_icb.csv").resolve()),
        },
        "configuration": config.to_dict(),
        "price_adjustment_policy": config.price_adjustment_policy,
        "promotion_status": quality["promotion_status"],
        "primary_key": ["symbol", "date"],
        "feature_columns": selected_features,
        "raw_columns_not_for_model": sorted(RAW_COLUMNS),
        "partitioning": "stock_features/year=YYYY/features.parquet",
        "label_policy": "Labels are not generated or stored by this pipeline.",
    }
    write_json(manifest, run_dir / "feature_manifest.json")
    run_dir.rename(final_run_dir)
    write_json(
        {
            "feature_version": config.feature_version,
            "run_id": run_id,
            "run_directory": str(final_run_dir.resolve()),
            "generated_at_utc": generated_at,
        },
        args.output_root / config.feature_version / "latest.json",
    )
    print(json.dumps(quality, ensure_ascii=False, indent=2), flush=True)
    print(f"Feature store: {final_run_dir.resolve()}", flush=True)


if __name__ == "__main__":
    main()
