"""Promote a hash-pinned V6 calibration-refit candidate into the advisory release."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def record(path: Path, *, rows: int | None = None) -> dict:
    value = {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": sha256(path),
        "size_bytes": path.stat().st_size,
    }
    if rows is not None:
        value["rows"] = rows
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--deploy-dir", type=Path, default=Path("deploy/wave_v6_advisory"))
    parser.add_argument("--model-destination", type=Path, default=Path("models_wave_v6/evaluation_bundle.joblib"))
    parser.add_argument("--lstm-excluded")
    parser.add_argument("--lstm-replacement")
    args = parser.parse_args()

    candidate = (ROOT / args.candidate_dir).resolve() if not args.candidate_dir.is_absolute() else args.candidate_dir
    deploy = (ROOT / args.deploy_dir).resolve() if not args.deploy_dir.is_absolute() else args.deploy_dir
    model_destination = (ROOT / args.model_destination).resolve() if not args.model_destination.is_absolute() else args.model_destination
    source_predictions = candidate / "latest_probability_before_after.csv"
    source_bundle = candidate / "evaluation_bundle_refit_calibration.joblib"
    report = candidate / "calibration_refit_report.json"
    for path in (source_predictions, source_bundle, report):
        if not path.is_file():
            raise FileNotFoundError(path)

    frame = pd.read_csv(source_predictions)
    required = {"rank_refit", "time", "ticker", "p_refit_pct"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Candidate prediction input is missing columns: {sorted(missing)}")
    frame = frame.rename(columns={"rank_refit": "rank"}).copy()
    frame["ticker"] = frame["ticker"].astype(str).str.strip().str.upper()
    frame["rank"] = pd.to_numeric(frame["rank"], errors="raise").astype(int)
    frame["p_ensemble"] = pd.to_numeric(frame["p_refit_pct"], errors="raise") / 100.0
    frame = frame.sort_values(["rank", "ticker"], kind="stable").drop_duplicates("ticker")
    raw_top50 = frame.head(50)
    if len(frame) < 50 or raw_top50["rank"].tolist() != list(range(1, 51)):
        raise ValueError("Candidate does not contain a complete rank-ordered Top 50.")
    if bool(args.lstm_excluded) != bool(args.lstm_replacement):
        raise ValueError("Provide both LSTM substitution arguments or neither.")
    excluded = str(args.lstm_excluded or "").strip().upper()
    replacement = str(args.lstm_replacement or "").strip().upper()
    if excluded:
        if excluded not in set(raw_top50["ticker"]) or replacement in set(raw_top50["ticker"]):
            raise ValueError("The declared LSTM substitution is not valid for the candidate Top 50.")
        if replacement not in set(frame["ticker"]):
            raise ValueError("The LSTM replacement is absent from the candidate universe.")

    deploy.mkdir(parents=True, exist_ok=True)
    model_destination.parent.mkdir(parents=True, exist_ok=True)
    prediction_path = deploy / "predictions.csv"
    prediction_tmp = prediction_path.with_suffix(".csv.tmp")
    frame.to_csv(prediction_tmp, index=False)
    prediction_tmp.replace(prediction_path)
    bundle_tmp = model_destination.with_suffix(model_destination.suffix + ".tmp")
    shutil.copy2(source_bundle, bundle_tmp)
    bundle_tmp.replace(model_destination)

    as_of = str(raw_top50.iloc[0]["time"])[:10]
    top50_payload = {
        "schema_version": 1,
        "release_id": "wave_v6_long_term_advisory_20260827_calibration11aug",
        "release_kind": "long_term_ensemble_top50",
        "as_of_date": as_of,
        "snapshot_date": as_of,
        "source_prediction_output": record(prediction_path, rows=len(frame)),
        "symbols": [
            {
                "rank": int(row.rank),
                "ticker": row.ticker,
                "date": str(row.time)[:10],
                "p_ensemble": float(row.p_ensemble),
            }
            for row in raw_top50.itertuples(index=False)
        ],
    }
    if excluded:
        top50_payload["lstm_substitution"] = {
            "excluded": excluded,
            "replacement": replacement,
            "reason": "The excluded symbol has insufficient history for the hybrid LSTM minimum sequence requirement.",
        }
    top50_path = deploy / "top50.json"
    write_json(top50_path, top50_payload)
    release = {
        "schema_version": 1,
        "release_id": "wave_v6_long_term_advisory_20260827_calibration11aug",
        "release_kind": "production_serving_advisory",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_evaluation_report": record(report),
        "model_bundle": record(model_destination),
        "snapshot_date": as_of,
        "as_of_date": as_of,
        "prediction_output": record(prediction_path, rows=len(frame)),
        "top50_output": record(top50_path, rows=len(raw_top50)),
        "contract": {
            "target": "unbounded_early_major_wave_vs_confirmed_structural_breakdown",
            "fixed_horizon_sessions": None,
            "probability_field": "long_term_trend_probability",
            "ranking_field": "long_term_rank",
            "advisory_only": True,
            "trade_authorized": False,
            "independent_from_h120": True,
            "serving_access": "premium_and_admin",
        },
        "limitations": [
            "The score is a long-term model advisory, not a forecast for a fixed date.",
            "The release does not authorize trades or combine V6 output with H120 output.",
        ],
    }
    write_json(deploy / "serving_release.json", release)
    print(json.dumps({"release_id": release["release_id"], "as_of_date": as_of, "prediction_rows": len(frame)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
