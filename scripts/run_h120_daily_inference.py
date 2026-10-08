"""Run deterministic daily inference from a frozen H120 deployment bundle."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.models.wave_production import (  # noqa: E402
    FrozenH120Runtime,
    score_h120_daily,
    sha256_file,
)


def discover_feature_files(source: Path, as_of_date: str | None) -> list[Path]:
    source = source.resolve()
    if source.is_file():
        if source.suffix.lower() not in {".parquet", ".csv"}:
            raise ValueError("Feature input must be Parquet or CSV.")
        return [source]
    if not source.is_dir():
        raise FileNotFoundError(f"Feature source does not exist: {source}")
    candidates = sorted(source.glob("stock_features/year=*/features.parquet"))
    if not candidates:
        candidates = sorted(source.glob("year=*/features.parquet"))
    if not candidates:
        candidates = sorted(source.rglob("features.parquet"))
    if not candidates:
        raise FileNotFoundError(f"No partitioned feature files found in {source}")
    target_year = pd.Timestamp(as_of_date).year if as_of_date else None
    if target_year is not None:
        candidates = [
            path for path in candidates if path.parent.name == f"year={target_year}"
        ]
        if not candidates:
            raise FileNotFoundError(f"No feature partition exists for year={target_year}")
    else:
        latest_year = max(int(path.parent.name.split("=", 1)[1]) for path in candidates)
        candidates = [
            path for path in candidates if path.parent.name == f"year={latest_year}"
        ]
    return candidates


def load_features(paths: list[Path]) -> pd.DataFrame:
    frames = [
        pd.read_parquet(path) if path.suffix.lower() == ".parquet" else pd.read_csv(path)
        for path in paths
    ]
    return pd.concat(frames, ignore_index=True)


def discover_feature_manifest(source: Path, explicit: Path | None) -> Path | None:
    if explicit is not None:
        return explicit.resolve()
    start = source.resolve() if source.is_dir() else source.resolve().parent
    for parent in (start, *start.parents):
        candidate = parent / "feature_manifest.json"
        if candidate.is_file():
            return candidate
        if parent == ROOT:
            break
    return None


def input_record(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    try:
        display = resolved.relative_to(ROOT).as_posix()
    except ValueError:
        display = str(resolved)
    return {
        "path": display,
        "size_bytes": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bundle",
        type=Path,
        default=Path("deploy/wave_h120_shadow/bundle_manifest.json"),
    )
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--feature-manifest", type=Path)
    parser.add_argument("--as-of-date")
    parser.add_argument(
        "--output-root", type=Path, default=Path("predictions/wave_h120_daily")
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    runtime = FrozenH120Runtime.from_manifest(args.bundle, project_root=ROOT)
    feature_files = discover_feature_files(args.features, args.as_of_date)
    feature_manifest = discover_feature_manifest(args.features, args.feature_manifest)
    if feature_manifest is None:
        raise RuntimeError("feature_manifest.json is required for inference lineage.")
    feature_metadata = json.loads(feature_manifest.read_text(encoding="utf-8"))
    if feature_metadata.get("feature_version") != runtime.contract["feature_version"]:
        raise RuntimeError("Feature manifest version does not match the frozen bundle.")
    if feature_metadata.get("feature_columns") != runtime.contract["feature_columns"]:
        raise RuntimeError("Feature manifest schema does not match the frozen bundle.")

    features = load_features(feature_files)
    predictions, summary = score_h120_daily(
        runtime, features, as_of_date=args.as_of_date
    )
    run_dir = args.output_root.resolve() / summary["as_of_date"]
    if run_dir.exists() and not args.overwrite:
        raise FileExistsError(f"Refusing to overwrite inference run: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)
    output_path = run_dir / "predictions.parquet"
    temporary_output = run_dir / "predictions.tmp.parquet"
    predictions.to_parquet(temporary_output, index=False)
    temporary_output.replace(output_path)

    manifest = {
        "schema_version": 1,
        "mode": "daily_h120_shadow_inference",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "deployment_status": runtime.manifest["deployment_status"],
        "trade_authorized": runtime.manifest["deployment_status"]
        == "production_approved",
        "bundle": input_record(args.bundle),
        "bundle_id": runtime.manifest["bundle_id"],
        "contract": runtime.contract,
        "feature_manifest": input_record(feature_manifest),
        "feature_inputs": [input_record(path) for path in feature_files],
        "summary": summary,
        "output": input_record(output_path),
        "columns": list(predictions.columns),
    }
    manifest_path = run_dir / "prediction_manifest.json"
    temporary_manifest = run_dir / "prediction_manifest.tmp.json"
    temporary_manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary_manifest.replace(manifest_path)
    print(
        json.dumps(
            {
                "status": "inference_complete",
                "deployment_status": manifest["deployment_status"],
                "as_of_date": summary["as_of_date"],
                "eligible_rows": summary["eligible_rows"],
                "shortlist_rows": summary["shortlist_rows"],
                "output": str(output_path),
                "manifest": str(manifest_path),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
