"""Export frozen upstream predictions on one untouched final population.

The cascade final frame is anchored on the H120 final split.  Each upstream
model is therefore loaded from its already-fitted deployment artifact and
scored on the exact H120 final rows.  No labels are used for prediction; the
H120 target and sample weights are copied only into the anchor output so the
downstream evaluation can be audited.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.models.wave_xgboost import WaveXGBoostPredictor  # noqa: E402
from src.training import subset_by_keys  # noqa: E402


MODEL_IDENTITY_FILES = (
    "model/entry_classifier.json",
    "model/strength_regressor.json",
    "model/calibration.json",
    "model/features.json",
)


def model_artifact_fingerprint(model_run: Path) -> str:
    """Fingerprint the deployable model payload, independent of its run name."""

    digest = hashlib.sha256()
    found = 0
    for relative in MODEL_IDENTITY_FILES:
        path = model_run / relative
        if not path.is_file():
            continue
        found += 1
        digest.update(relative.encode("utf-8"))
        digest.update(path.read_bytes())
    if not found:
        raise FileNotFoundError(f"No deployable model files found in {model_run}")
    return digest.hexdigest()


def validate_distinct_model_roles(model_runs: dict[str, Path]) -> dict[str, str]:
    """Reject copied artifacts masquerading as distinct semantic heads."""

    fingerprints = {
        role: model_artifact_fingerprint(path.resolve())
        for role, path in model_runs.items()
    }
    roles = list(fingerprints)
    duplicates = [
        (left, right)
        for index, left in enumerate(roles)
        for right in roles[index + 1 :]
        if fingerprints[left] == fingerprints[right]
    ]
    if duplicates:
        raise RuntimeError(
            "Different head roles resolve to identical model artifacts: "
            f"{duplicates}. Fix model lineage before exporting predictions."
        )
    return fingerprints


def load_dataset(run: Path) -> pd.DataFrame:
    partitions = sorted(run.glob("dataset/year=*/dataset.parquet"))
    if not partitions:
        raise RuntimeError(f"No dataset partitions found in {run}")
    frame = pd.concat((pd.read_parquet(path) for path in partitions), ignore_index=True)
    frame["date"] = pd.to_datetime(frame["date"], errors="raise")
    if frame.duplicated(["symbol", "date"]).any():
        raise RuntimeError("Dataset contains duplicate symbol/date keys.")
    frame.sort_values(["date", "symbol"], kind="stable", inplace=True)
    frame.set_index(["symbol", "date"], verify_integrity=True, inplace=True)
    return frame


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--anchor-dataset-run", type=Path, required=True)
    parser.add_argument("--h120-model", type=Path, required=True)
    parser.add_argument("--h60-model", type=Path)
    parser.add_argument("--h20-model", type=Path)
    parser.add_argument("--v6-model", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def export_one(
    final_rows: pd.DataFrame,
    model_run: Path,
    output_path: Path,
    *,
    artifact_fingerprint: str,
    include_anchor_target: bool,
) -> dict[str, object]:
    predictor = WaveXGBoostPredictor.from_run(model_run)
    predictions = predictor.predict(final_rows)
    if include_anchor_target:
        required = {"y_entry", "sample_weight"}
        missing = sorted(required - set(final_rows.columns))
        if missing:
            raise RuntimeError(f"H120 anchor dataset is missing {missing}")
        predictions["y_entry"] = final_rows["y_entry"].to_numpy()
        predictions["sample_weight"] = final_rows["sample_weight"].to_numpy()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    predictions.to_parquet(output_path, index=False)
    return {
        "model_run": str(model_run.resolve()),
        "output": str(output_path.resolve()),
        "rows": int(len(predictions)),
        "columns": list(predictions.columns),
        "feature_columns": predictor.feature_columns,
        "model_version": predictor.model_manifest.get("model_version"),
        "run_id": predictor.model_manifest.get("run_id"),
        "artifact_fingerprint": artifact_fingerprint,
    }


def main() -> int:
    args = parse_args()
    anchor_run = args.anchor_dataset_run.resolve()
    dataset = load_dataset(anchor_run)
    final_rows = subset_by_keys(dataset, anchor_run / "splits/final/test_keys.parquet")
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    model_runs = {"h120": args.h120_model.resolve()}
    for role, model_run in (
        ("h60", args.h60_model),
        ("h20", args.h20_model),
        ("v6_trend", args.v6_model),
    ):
        if model_run is not None:
            model_runs[role] = model_run.resolve()
    fingerprints = validate_distinct_model_roles(model_runs)

    outputs = {
        "h120": export_one(
            final_rows,
            model_runs["h120"],
            output_dir / "h120_final_predictions.parquet",
            artifact_fingerprint=fingerprints["h120"],
            include_anchor_target=True,
        )
    }
    for role, filename in (
        ("h60", "h60_final_predictions.parquet"),
        ("h20", "h20_final_predictions.parquet"),
        ("v6_trend", "v6_trend_final_predictions.parquet"),
    ):
        if role not in model_runs:
            continue
        outputs[role] = export_one(
            final_rows,
            model_runs[role],
            output_dir / filename,
            artifact_fingerprint=fingerprints[role],
            include_anchor_target=False,
        )
    manifest = {
        "schema_version": 2,
        "mode": "final_test_predictions",
        "head_contract": list(outputs),
        "final_holdout_opened": True,
        "anchor_dataset_run": str(anchor_run),
        "anchor_rows": int(len(final_rows)),
        "anchor_dates": sorted(pd.to_datetime(final_rows["date"]).dt.strftime("%Y-%m-%d").unique().tolist()),
        "outputs": outputs,
        "warning": "Predictions are frozen upstream outputs; do not use this population for model or policy selection.",
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
