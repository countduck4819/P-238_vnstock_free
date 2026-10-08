"""Score a dated V6 snapshot using only the locked production bundle.

This command never trains, tunes, calibrates, or overwrites model artifacts.
It builds point-in-time features only, writes a hash-verified run artifact, and
keeps a failed run isolated from the latest servable result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
V6_SCRIPT_DIR = ROOT / "scripts" / "wave_v6"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(V6_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(V6_SCRIPT_DIR))

from train_v6_original_shadow import (  # noqa: E402
    Config,
    MODEL_NAMES,
    apply_individual_calibrators,
    apply_platt,
    build_latest_ranking,
    build_panel,
    raw_probability_matrix,
)


class V6DailyInferenceError(RuntimeError):
    """Raised when a daily V6 inference run violates its frozen contract."""


def _path(value: Path) -> Path:
    return value if value.is_absolute() else ROOT / value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _record(path: Path) -> dict[str, Any]:
    path = path.resolve()
    try:
        display = path.relative_to(ROOT).as_posix()
    except ValueError:
        display = str(path)
    return {"path": display, "size_bytes": path.stat().st_size, "sha256": _sha256(path)}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    temporary.replace(path)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise V6DailyInferenceError(f"Cannot read JSON: {path}") from exc
    if not isinstance(value, dict):
        raise V6DailyInferenceError(f"JSON must be an object: {path}")
    return value


def _locked_bundle(bundle_path: Path, release_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    release = _read_json(release_path)
    contract = release.get("contract", {})
    if (
        release.get("release_kind") != "production_serving_advisory"
        or contract.get("trade_authorized") is not False
        or contract.get("independent_from_h120") is not True
        or contract.get("fixed_horizon_sessions", "missing") is not None
    ):
        raise V6DailyInferenceError("V6 serving release contract is invalid.")
    expected = str(release.get("model_bundle", {}).get("sha256", "")).lower()
    actual = _sha256(bundle_path).lower()
    if not expected or actual != expected:
        raise V6DailyInferenceError("V6 bundle hash does not match the serving release.")
    bundle = joblib.load(bundle_path)
    required = {"models", "individual_calibrators", "ensemble_calibrator", "ensemble_weights", "feature_processor", "config"}
    if not isinstance(bundle, dict) or required.difference(bundle):
        raise V6DailyInferenceError("V6 bundle is incomplete.")
    return release, bundle


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, default=Path("models_wave_v6/evaluation_bundle.joblib"))
    parser.add_argument("--release", type=Path, default=Path("deploy/wave_v6_advisory/serving_release.json"))
    parser.add_argument("--run-root", type=Path, default=Path("runs/wave_v6_daily"))
    parser.add_argument("--snapshot-date")
    parser.add_argument("--allow-stale-cache", action="store_true", help="Only for historical replay/testing.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    snapshot_dir = _path(args.snapshot_dir).resolve()
    bundle_path = _path(args.bundle).resolve()
    release_path = _path(args.release).resolve()
    manifest_path = snapshot_dir / "snapshot_manifest.json"
    if not manifest_path.is_file():
        raise V6DailyInferenceError("Snapshot manifest is required for daily scoring.")
    snapshot_manifest = _read_json(manifest_path)
    snapshot_date = args.snapshot_date or str(snapshot_manifest.get("requested_as_of_end", ""))
    if not snapshot_date:
        raise V6DailyInferenceError("Snapshot manifest has no requested_as_of_end.")
    release, bundle = _locked_bundle(bundle_path, release_path)
    cfg_values = dict(bundle["config"])
    cfg = Config(**cfg_values)
    cfg = replace(
        cfg,
        data_dir=str(snapshot_dir),
        market_path=str(snapshot_dir / "market" / "VNINDEX.csv"),
        industry_path=str(snapshot_dir / "industry_map.csv"),
        market_cap_path=str(snapshot_dir / "symbols.csv"),
        latest_top_n=100_000,
    )

    panel, data_meta, ticker_quality = build_panel(
        cfg, allow_stale_cache=args.allow_stale_cache, include_targets=False
    )
    features = list(bundle["feature_processor"]["features"])
    latest_candidates = panel.loc[panel["eligible"].fillna(False)].copy()
    latest_candidates = latest_candidates.loc[
        latest_candidates[features].notna().mean(axis=1) >= cfg.min_row_feature_coverage
    ]
    latest_date = pd.Timestamp(latest_candidates["time"].max())
    latest = latest_candidates.loc[latest_candidates["time"].eq(latest_date)].copy()
    if len(latest) < cfg.min_latest_symbols:
        raise V6DailyInferenceError(
            f"Only {len(latest)} eligible symbols share the latest scoring date; minimum is {cfg.min_latest_symbols}."
        )
    raw = raw_probability_matrix(bundle["models"], latest, bundle["feature_processor"])
    calibrated = apply_individual_calibrators(raw, bundle["individual_calibrators"])
    weights = np.asarray([bundle["ensemble_weights"][name] for name in MODEL_NAMES], dtype=float)
    if not np.isclose(weights.sum(), 1.0):
        raise V6DailyInferenceError("V6 ensemble weights are invalid.")
    probability = apply_platt(bundle["ensemble_calibrator"], calibrated @ weights)
    ranked = build_latest_ranking(latest, calibrated, probability, weights, cfg)
    if ranked.empty or ranked["p_ensemble"].isna().any():
        raise V6DailyInferenceError("V6 scoring produced no valid probabilities.")

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = _path(args.run_root) / f"{snapshot_date}_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=False)
    output_path = run_dir / "predictions.csv"
    temporary = output_path.with_suffix(".tmp.csv")
    ranked.to_csv(temporary, index=False)
    temporary.replace(output_path)
    as_of_date = str(latest_date.date())
    manifest = {
        "schema_version": 1,
        "pipeline": "wave_v6_daily_inference",
        "run_id": run_id,
        "status": "success",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "snapshot_date": snapshot_date,
        "as_of_date": as_of_date,
        "trade_authorized": False,
        "independent_from_h120": True,
        "fixed_horizon_sessions": None,
        "source_release_id": release.get("release_id"),
        "model_bundle": _record(bundle_path),
        "snapshot_manifest": _record(manifest_path),
        "prediction_output": {**_record(output_path), "rows": int(len(ranked))},
        "summary": {
            "loaded_symbols": int(data_meta["loaded_symbols"]),
            "eligible_rows": int(len(ranked)),
            "top_probability": float(ranked["p_ensemble"].max()),
            "targets_calculated": False,
            "ticker_quality_rows": int(len(ticker_quality)),
        },
    }
    _write_json(run_dir / "orchestration_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
