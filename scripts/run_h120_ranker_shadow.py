"""Score a Phase-E H120 ranker bundle in shadow mode on a feature snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from xgboost import Booster, DMatrix


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-run", type=Path, required=True)
    parser.add_argument("--feature-run", type=Path, required=True)
    parser.add_argument("--as-of-date", required=True)
    parser.add_argument(
        "--output-root", type=Path, default=Path("predictions/h120_ranker_shadow_challenger")
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def main() -> int:
    args = parse_args()
    model_run = args.model_run.resolve()
    feature_run = args.feature_run.resolve()
    manifest_path = model_run / "model_manifest.json"
    model_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if model_manifest.get("trade_authorized", True):
        raise ValueError("Shadow scorer refuses a trade-authorized model bundle.")
    if model_manifest.get("ranking_policy") != "rank_score_only":
        raise ValueError("Shadow scorer requires the immutable rank_score-only contract.")
    feature_manifest_path = feature_run / "feature_manifest.json"
    feature_manifest = json.loads(feature_manifest_path.read_text(encoding="utf-8"))
    expected_feature_version = model_manifest["feature_dependency"]["version"]
    if feature_manifest.get("feature_version") != expected_feature_version:
        raise ValueError("Feature version does not match the refit model dependency.")
    features = json.loads((model_run / "feature_list.json").read_text(encoding="utf-8"))
    partition = feature_run / "stock_features" / f"year={pd.Timestamp(args.as_of_date).year}" / "features.parquet"
    frame = pd.read_parquet(partition)
    frame["date"] = pd.to_datetime(frame["date"], errors="raise")
    decision_date = pd.Timestamp(args.as_of_date)
    current = frame.loc[frame["date"].eq(decision_date)].copy()
    if current.empty:
        raise ValueError(f"No feature rows exist for {decision_date.date()}.")
    missing = sorted(set(features).difference(current.columns))
    if missing:
        raise ValueError(f"Feature snapshot is missing frozen columns: {missing}")
    eligible = current.loc[current["feature_ready"].eq(True)].copy()
    finite = np.isfinite(eligible[features].to_numpy(dtype=float)).all(axis=1)
    eligible = eligible.loc[finite].copy()
    if eligible.empty:
        raise ValueError("No finite feature-ready rows are eligible for challenger shadow scoring.")
    booster = Booster()
    model_path = model_run / "model" / "ranker.json"
    booster.load_model(model_path)
    eligible["rank_score"] = booster.predict(DMatrix(eligible[features], feature_names=features))
    eligible.sort_values(["rank_score", "symbol"], ascending=[False, True], kind="stable", inplace=True)
    eligible["rank"] = np.arange(1, len(eligible) + 1)
    eligible["is_top_10"] = eligible["rank"].le(10)
    output = eligible.loc[:, ["symbol", "date", "rank_score", "rank", "is_top_10"]]
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    final = args.output_root.resolve() / f"{decision_date.date()}_{run_id}"
    incomplete = final.parent / f".incomplete-{final.name}"
    incomplete.mkdir(parents=True, exist_ok=False)
    output.to_parquet(incomplete / "predictions.parquet", index=False)
    result_manifest = {
        "status": "shadow_challenger_scored_not_trade_authorized",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "as_of_date": str(decision_date.date()),
        "model_run": str(model_run),
        "feature_run": str(feature_run),
        "input_checksums": {
            "model_manifest": sha256(manifest_path),
            "ranker": sha256(model_path),
            "feature_manifest": sha256(feature_manifest_path),
            "feature_partition": sha256(partition),
        },
        "summary": {
            "input_rows": int(len(current)),
            "eligible_rows": int(len(output)),
            "shortlist_rows": int(output["is_top_10"].sum()),
            "top_10_symbols": output.loc[output["is_top_10"], "symbol"].tolist(),
        },
        "ranking_policy": "rank_score_only",
        "probability_status": model_manifest["calibration_status"],
        "trade_authorized": False,
    }
    (incomplete / "prediction_manifest.json").write_text(
        json.dumps(result_manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    incomplete.rename(final)
    print(json.dumps({"status": result_manifest["status"], "run_directory": str(final)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
